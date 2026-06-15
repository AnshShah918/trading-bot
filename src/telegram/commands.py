import os
from datetime import datetime, timezone, timedelta
from telegram import Update
from telegram.ext import (
    ContextTypes,
    CommandHandler
)

from src.memory.trade_repository import (
    get_open_trades,
    get_closed_trades,
    close_trade,
    update_trade_net_pnl
)
from src.portfolio.portfolio_manager import PortfolioManager
from src.utils.cost_calculator import calculate_trade_costs
from src.utils.trading_calendar import is_t1_ready, is_trading_day

portfolio = PortfolioManager()


async def cmd_help(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "🤖 *Bot Commands*\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "📊 */status*\n"
        "Open trades with live P&L,\n"
        "stop loss and T+1 status\n\n"
        "💼 */portfolio*\n"
        "Full capital summary\n\n"
        "🔍 */scan*\n"
        "Manually trigger a scan now\n\n"
        "📰 */news*\n"
        "Todays thematic market themes\n\n"
        "🔄 */refresh*\n"
        "Fetch latest prices for open positions\n\n"
        "❌ */close 42 512.50*\n"
        "Manually close trade 42 at 512.50\n\n"
        "✅ */confirm 42 512.50*\n"
        "Confirm manual sell on Zerodha\n\n"
        "⏸ */pause*\n"
        "Stop bot opening new trades\n\n"
        "▶️ */resume*\n"
        "Allow new trades again\n\n"
        "❓ */help*\n"
        "This message\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "All trades are PAPER only.",
        parse_mode="Markdown"
    )


async def cmd_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    trades = get_open_trades()

    if not trades:
        await update.message.reply_text(
            "📭 No open trades right now."
        )
        return

    market_open = is_trading_day()
    price_note = (
        "live prices"
        if market_open
        else "last known — market closed"
    )

    lines = [
        f"📊 *Open Trades* ({price_note})\n"
        "━━━━━━━━━━━━━━━━━━"
    ]

    total_unrealised = 0

    for t in trades:

        hold_days = (
            datetime.now() - t.entry_time
        ).days if t.entry_time else 0

        t1_status = (
            "✅ T+1 ready"
            if is_t1_ready(t.entry_time)
            else "⏳ T+1 pending"
        )

        last_price = (
            t.last_known_price
            or t.entry_price
        )

        unrealised = (
            (last_price - t.entry_price)
            * t.quantity
        )

        unrealised_pct = (
            (last_price - t.entry_price)
            / t.entry_price * 100
        )

        total_unrealised += unrealised
        emoji = "📈" if unrealised >= 0 else "📉"

        lines.append(
            f"\n*#{t.id} {t.symbol}*\n"
            f"Entry:       ₹{t.entry_price} "
            f"x {t.quantity} shares\n"
            f"Last price:  ₹{last_price}\n"
            f"Unrealised:  {emoji} "
            f"₹{round(unrealised, 0):,.0f} "
            f"({round(unrealised_pct, 2)}%)\n"
            f"Stop:        "
            f"₹{round(t.current_stop, 2) if t.current_stop else 'N/A'}\n"
            f"Held:        {hold_days}d — {t1_status}"
        )

    total_emoji = "📈" if total_unrealised >= 0 else "📉"

    lines.append(
        f"\n━━━━━━━━━━━━━━━━━━\n"
        f"Total unrealised: "
        f"{total_emoji} ₹{round(total_unrealised, 0):,.0f}\n"
        f"📝 Paper trades only"
    )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown"
    )


async def cmd_portfolio(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    closed = get_closed_trades()
    open_trades = get_open_trades()

    total_realised = sum(
        (
            t.net_pnl
            if t.net_pnl is not None
            else t.pnl
        )
        for t in closed
        if t.pnl is not None
    )

    total_unrealised = sum(
        (
            (t.last_known_price or t.entry_price)
            - t.entry_price
        ) * t.quantity
        for t in open_trades
    )

    total_charges = 0
    tax_reserve = 0

    for t in closed:
        if t.pnl and t.entry_price and t.exit_price:
            costs = calculate_trade_costs(
                t.entry_price * t.quantity,
                t.exit_price * t.quantity,
                t.pnl
            )
            total_charges += costs["charges"]
            tax_reserve += (
                costs["estimated_tax_reserve"]
            )

    hold_days_list = [
        (t.exit_time - t.entry_time).days
        for t in closed
        if t.exit_time and t.entry_time
    ]

    stcg = sum(1 for d in hold_days_list if d < 365)
    ltcg = sum(1 for d in hold_days_list if d >= 365)

    mode = (
        "🔴 RECOVERY"
        if portfolio.current_capital
        < portfolio.base_capital
        else "🟢 NORMAL"
    )

    deployed = sum(
        t.entry_price * t.quantity
        for t in open_trades
    )

    await update.message.reply_text(
        f"💼 *Portfolio Summary*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Capital:        ₹{portfolio.current_capital:,.0f}\n"
        f"Deployed:       ₹{deployed:,.0f}\n"
        f"Base:           ₹{portfolio.base_capital:,.0f}\n"
        f"Booked profit:  ₹{portfolio.booked_profit:,.0f}\n"
        f"Mode:           {mode}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Realised P&L:   ₹{total_realised:,.0f}\n"
        f"Unrealised P&L: ₹{round(total_unrealised, 0):,.0f}\n"
        f"Charges:        ₹{total_charges:,.0f}\n"
        f"Tax reserve:    ₹{tax_reserve:,.0f}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"STCG trades:    {stcg}\n"
        f"LTCG trades:    {ltcg}\n"
        f"Open:           {len(open_trades)}\n"
        f"Closed:         {len(closed)}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📝 Paper trades only",
        parse_mode="Markdown"
    )


async def cmd_close(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    args = context.args

    if not args:
        await update.message.reply_text(
            "Usage: /close <trade_id> <exit_price>\n"
            "Example: /close 42 512.50"
        )
        return

    try:
        trade_id = int(args[0])
        exit_price = float(args[1])
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Invalid format.\n"
            "Usage: /close 42 512.50"
        )
        return

    trade = close_trade(
        trade_id,
        exit_price,
        exit_reason="manual_close"
    )

    if not trade:
        await update.message.reply_text(
            f"Trade {trade_id} not found."
        )
        return

    costs = calculate_trade_costs(
        trade.entry_price * trade.quantity,
        trade.exit_price * trade.quantity,
        trade.pnl
    )
    portfolio.apply_trade_result(
        costs["net_pnl"]
    )
    update_trade_net_pnl(
        trade.id,
        costs["net_pnl"]
    )

    hold_days = (
        trade.exit_time - trade.entry_time
    ).days if trade.exit_time and trade.entry_time else 0

    tax_type = (
        "LTCG 12.5%" if hold_days >= 365
        else "STCG 20%"
    )

    await update.message.reply_text(
        f"✅ *Trade {trade_id} Closed*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Symbol:    {trade.symbol}\n"
        f"Entry:     ₹{trade.entry_price}\n"
        f"Exit:      ₹{exit_price}\n"
        f"Held:      {hold_days} days\n"
        f"Gross P&L: ₹{trade.pnl:,.0f}\n"
        f"Charges:   ₹{costs['charges']}\n"
        f"Net P&L:   ₹{costs['net_pnl']:,.0f}\n"
        f"Tax type:  {tax_type}\n"
        f"Reserve:   ₹{costs['estimated_tax_reserve']:,.0f}\n"
        f"📝 Paper trade only",
        parse_mode="Markdown"
    )


async def cmd_confirm(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    args = context.args

    if not args or len(args) < 2:
        await update.message.reply_text(
            "Usage: /confirm <trade_id> <exit_price>\n"
            "Example: /confirm 3 245.50\n"
            "Use after manually selling on Zerodha."
        )
        return

    try:
        trade_id = int(args[0])
        exit_price = float(args[1])
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Invalid format.\n"
            "Usage: /confirm 3 245.50"
        )
        return

    from src.monitor.sell_manager import _queued_sells
    _queued_sells.pop(trade_id, None)

    trade = close_trade(
        trade_id,
        exit_price,
        exit_reason="manual_confirm"
    )

    if not trade:
        await update.message.reply_text(
            f"Trade {trade_id} not found."
        )
        return

    costs = calculate_trade_costs(
        trade.entry_price * trade.quantity,
        exit_price * trade.quantity,
        trade.pnl
    )
    portfolio.apply_trade_result(
        costs["net_pnl"]
    )
    update_trade_net_pnl(
        trade.id,
        costs["net_pnl"]
    )

    await update.message.reply_text(
        f"✅ *Trade {trade_id} Confirmed*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Symbol:    {trade.symbol}\n"
        f"Exit:      ₹{exit_price}\n"
        f"Net P&L:   ₹{costs['net_pnl']:,.0f}\n"
        f"Charges:   ₹{costs['charges']}\n"
        f"Removed from pending sells.",
        parse_mode="Markdown"
    )


async def cmd_pause(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "⏸ Bot paused.\n"
        "No new trades will open.\n"
        "Monitoring continues.\n"
        "Send /resume to restart."
    )
    context.bot_data["paused"] = True


async def cmd_resume(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.bot_data["paused"] = False
    await update.message.reply_text(
        "▶️ Bot resumed. Ready for new trades."
    )


async def cmd_refresh(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "🔄 Fetching latest prices..."
    )

    from src.monitor.position_monitor import (
        refresh_open_positions
    )

    bot_token_map = context.bot_data.get(
        "token_map", {}
    )

    await refresh_open_positions(
        update.get_bot(),
        bot_token_map
    )


async def cmd_news(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "📰 Searching todays market news...\n"
        "This may take 15-20 seconds."
    )

    from src.news.thematic_scanner import (
        get_thematic_alerts,
        format_theme_message
    )

    themes, error = get_thematic_alerts()

    if themes is None:
        await update.message.reply_text(
            f"News search failed: {error}"
        )
        return

    if not themes:
        await update.message.reply_text(
            f"📭 {error}\n"
            f"No major themes today."
        )
        return

    await update.message.reply_text(
        f"📰 *{len(themes)} Theme(s) Found*\n"
        f"Watch alerts — not trade signals.\n"
        f"Research before acting.",
        parse_mode="Markdown"
    )

    for theme in themes:
        try:
            await update.message.reply_text(
                format_theme_message(theme),
                parse_mode="MarkdownV2"
            )
        except Exception:
            # Fallback plain text
            stocks = ", ".join(
                theme.get("stocks", [])
            )
            await update.message.reply_text(
                f"{theme.get('urgency')} — "
                f"{theme.get('theme')}\n\n"
                f"{theme.get('summary')}\n\n"
                f"Stocks: {stocks}\n"
                f"Verify: {theme.get('source_hint')}"
            )

    await update.message.reply_text(
        "Use /scan after researching a theme."
    )


async def cmd_why(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    args = context.args

    if not args:
        await update.message.reply_text(
            "Usage: /why <symbol>\n"
            "Example: /why BELRISE"
        )
        return

    symbol = args[0].upper()

    await update.message.reply_text(
        f"Checking {symbol}..."
    )

    try:
        from kiteconnect import KiteConnect
        from src.universe.instrument_lookup import (
            InstrumentLookup
        )
        from src.scanner.momentum_scanner import (
            MomentumScanner
        )

        kite = KiteConnect(
            api_key=os.getenv("KITE_API_KEY")
        )
        kite.set_access_token(
            os.getenv("KITE_ACCESS_TOKEN")
        )

        instruments = kite.instruments("NSE")
        token_map = InstrumentLookup.build_map(
            instruments
        )
        token = token_map.get(symbol)

        if not token:
            await update.message.reply_text(
                f"{symbol} not found in Kite NSE instruments."
            )
            return

        to_date = datetime.now()
        from_date = to_date - timedelta(days=365)
        candles = kite.historical_data(
            instrument_token=token,
            from_date=from_date,
            to_date=to_date,
            interval="day"
        )

        if not candles:
            await update.message.reply_text(
                f"No daily candle data found for {symbol}."
            )
            return

        setup = MomentumScanner().scan(
            symbol=symbol,
            candles=candles,
            available_capital=portfolio.current_capital
        )

        reasons = setup.get(
            "rejection_reasons", []
        )
        reason_text = (
            ", ".join(reasons)
            if reasons else "none"
        )

        await update.message.reply_text(
            f"*{symbol} Scanner Check*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Tier: {setup['tier']}\n"
            f"Score: {setup['score']}\n"
            f"Risk-adj: {setup['risk_adj_score']}\n"
            f"RSI: {setup['rsi']}\n"
            f"Momentum: {setup['momentum']}\n"
            f"Volume: {setup['volume_ratio']}x\n"
            f"Risk: {setup['risk_pct']}%\n"
            f"Reasons: {reason_text}",
            parse_mode="Markdown"
        )

    except Exception as e:
        await update.message.reply_text(
            f"Could not check {symbol}: {e}"
        )


def register_commands(app):
    app.add_handler(
        CommandHandler("help", cmd_help)
    )
    app.add_handler(
        CommandHandler("status", cmd_status)
    )
    app.add_handler(
        CommandHandler("portfolio", cmd_portfolio)
    )
    app.add_handler(
        CommandHandler("close", cmd_close)
    )
    app.add_handler(
        CommandHandler("confirm", cmd_confirm)
    )
    app.add_handler(
        CommandHandler("pause", cmd_pause)
    )
    app.add_handler(
        CommandHandler("resume", cmd_resume)
    )
    app.add_handler(
        CommandHandler("refresh", cmd_refresh)
    )
    app.add_handler(
        CommandHandler("news", cmd_news)
    )
    app.add_handler(
        CommandHandler("why", cmd_why)
    )
