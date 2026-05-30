from datetime import datetime
from telegram import Update
from telegram.ext import (
    ContextTypes,
    CommandHandler
)

from src.memory.trade_repository import (
    get_open_trades,
    get_closed_trades,
    close_trade
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
        "Full capital summary —\n"
        "realised + unrealised P&L,\n"
        "tax reserve, charges\n\n"
        "🔍 */scan*\n"
        "Manually trigger a scan\n"
        "right now (any time)\n\n"
        "❌ */close 42 512.50*\n"
        "Manually close trade #42\n"
        "at exit price ₹512.50\n\n"
        "⏸ */pause*\n"
        "Stop bot opening new trades\n"
        "(monitoring continues)\n\n"
        "▶️ */resume*\n"
        "Allow new trades again\n\n"
        "❓ */help*\n"
        "This message\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💡 All trades are PAPER only.\n"
        "No real orders placed.",
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
        else "last known prices — market closed"
    )

    lines = [
        f"📊 *Open Trades* ({price_note})\n"
        "━━━━━━━━━━━━━━━━━━"
    ]

    total_unrealised = 0

    for t in trades:

        hold_days = (
            datetime.utcnow() - t.entry_time
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
            f"× {t.quantity} shares\n"
            f"Last price:  ₹{last_price}\n"
            f"Unrealised:  {emoji} "
            f"₹{round(unrealised, 0):,.0f} "
            f"({round(unrealised_pct, 2)}%)\n"
            f"Stop:        ₹{round(t.current_stop, 2) if t.current_stop else 'N/A'}\n"
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
        t.pnl for t in closed if t.pnl
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
            tax_reserve += costs["estimated_tax_reserve"]

    hold_days_list = [
        (t.exit_time - t.entry_time).days
        for t in closed
        if t.exit_time and t.entry_time
    ]

    stcg = sum(1 for d in hold_days_list if d < 365)
    ltcg = sum(1 for d in hold_days_list if d >= 365)

    mode = (
        "🔴 RECOVERY"
        if portfolio.current_capital < portfolio.base_capital
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
            "❌ Invalid format.\n"
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
            f"❌ Trade #{trade_id} not found."
        )
        return

    costs = calculate_trade_costs(
        trade.entry_price * trade.quantity,
        trade.exit_price * trade.quantity,
        trade.pnl
    )

    hold_days = (
        trade.exit_time - trade.entry_time
    ).days if trade.exit_time and trade.entry_time else 0

    tax_type = (
        "LTCG 12.5%" if hold_days >= 365
        else "STCG 20%"
    )

    await update.message.reply_text(
        f"✅ *Trade #{trade_id} Closed*\n"
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


def register_commands(app):
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("close", cmd_close))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
