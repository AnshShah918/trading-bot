from datetime import datetime, timezone
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


portfolio = PortfolioManager()


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

    lines = ["📊 *Open Trades*\n━━━━━━━━━━━━━━━━━━"]

    for t in trades:

        hold_days = (
            datetime.utcnow() - t.entry_time
        ).days if t.entry_time else 0

        t1_ready = "✅" if hold_days >= 1 else "⏳ T+1 pending"

        lines.append(
            f"\n*#{t.id} {t.symbol}*\n"
            f"Entry:   ₹{t.entry_price} × {t.quantity}\n"
            f"Stop:    ₹{round(t.current_stop, 2) if t.current_stop else 'N/A'}\n"
            f"Held:    {hold_days} day(s) {t1_ready}\n"
            f"Capital: ₹{round(t.entry_price * t.quantity, 2)}"
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

    total_pnl = sum(
        t.pnl for t in closed if t.pnl
    )

    total_charges = 0
    tax_reserve = 0

    for t in closed:
        if t.pnl and t.entry_price and t.exit_price:
            buy_val = t.entry_price * t.quantity
            sell_val = t.exit_price * t.quantity
            costs = calculate_trade_costs(
                buy_val, sell_val, t.pnl
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

    mode = "🔴 RECOVERY" if portfolio.current_capital < portfolio.base_capital else "🟢 NORMAL"

    await update.message.reply_text(
        f"💼 *Portfolio Summary*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Capital:      ₹{portfolio.current_capital:,.0f}\n"
        f"Base:         ₹{portfolio.base_capital:,.0f}\n"
        f"Booked:       ₹{portfolio.booked_profit:,.0f}\n"
        f"Mode:         {mode}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Gross P&L:    ₹{total_pnl:,.0f}\n"
        f"Charges:      ₹{total_charges:,.0f}\n"
        f"Tax reserve:  ₹{tax_reserve:,.0f}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"STCG trades:  {stcg}\n"
        f"LTCG trades:  {ltcg}\n"
        f"Total closed: {len(closed)}",
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

    tax_type = "LTCG 12.5%" if hold_days >= 365 else "STCG 20%"

    await update.message.reply_text(
        f"✅ *Trade #{trade_id} Closed*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Symbol:    {trade.symbol}\n"
        f"Entry:     ₹{trade.entry_price}\n"
        f"Exit:      ₹{exit_price}\n"
        f"Gross P&L: ₹{trade.pnl:,.0f}\n"
        f"Charges:   ₹{costs['charges']}\n"
        f"Net P&L:   ₹{costs['net_pnl']:,.0f}\n"
        f"Tax type:  {tax_type}\n"
        f"Reserve:   ₹{costs['estimated_tax_reserve']:,.0f}",
        parse_mode="Markdown"
    )


async def cmd_pause(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "⏸ Bot paused. No new trades will open.\n"
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
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("close", cmd_close))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
