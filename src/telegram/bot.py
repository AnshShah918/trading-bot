import os
import asyncio
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes
)

from src.telegram.notifier import send_setup, send_message
from src.telegram.commands import register_commands
from src.paper_trading.paper_engine import PaperEngine
from src.ai.analyser import analyse_setups, get_cost_summary

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")

paper = PaperEngine()
pending_setups = {}
sent_today = set()
token_map = {}


async def handle_decision(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if context.bot_data.get("paused"):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "⏸ Bot is paused. Send /resume first."
        )
        return

    query = update.callback_query
    await query.answer()

    action, symbol = query.data.split(":")
    setup = pending_setups.get(symbol)

    if action == "YES" and setup:

        trade = paper.open_position(
            symbol=symbol,
            entry_price=setup["current_price"],
            quantity=setup["shares_to_buy"],
            entry_reason=(
                f"score={setup['score']} "
                f"rsi={setup['rsi']} "
                f"ai={setup.get('ai_confidence', 'N/A')}"
            ),
            atr=setup["atr"],
            current_stop=setup["suggested_stop"]
        )

        await query.edit_message_text(
            f"✅ *{symbol}* — Trade Opened\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Entry:   ₹{setup['current_price']}\n"
            f"Shares:  {setup['shares_to_buy']}\n"
            f"Stop:    ₹{setup['suggested_stop']}\n"
            f"Trade ID: #{trade.id}",
            parse_mode="Markdown"
        )

        del pending_setups[symbol]

    elif action == "NO":

        await query.edit_message_text(
            f"❌ *{symbol}* — Skipped",
            parse_mode="Markdown"
        )

        if symbol in pending_setups:
            del pending_setups[symbol]


async def run_scan(application, scan_type="morning"):

    from kiteconnect import KiteConnect
    from src.universe.nifty500 import Nifty500
    from src.universe.instrument_lookup import InstrumentLookup
    from src.scanner.momentum_scanner import MomentumScanner

    global token_map

    bot = application.bot

    label = {
        "morning": "🌅 Morning",
        "midday": "☀️ Mid-day",
        "closing": "🌆 Closing"
    }.get(scan_type, "")

    await send_message(
        bot,
        f"{label} scan starting..."
    )

    kite = KiteConnect(
        api_key=os.getenv("KITE_API_KEY")
    )
    kite.set_access_token(
        os.getenv("KITE_ACCESS_TOKEN")
    )

    instruments = kite.instruments("NSE")
    token_map = InstrumentLookup.build_map(instruments)
    watchlist = Nifty500.load()
    scanner = MomentumScanner()

    to_date = datetime.now()
    from_date = to_date - timedelta(days=365)

    results = []

    def scan_symbol(symbol):
        token = token_map.get(symbol)
        if not token:
            return None
        try:
            candles = kite.historical_data(
                instrument_token=token,
                from_date=from_date,
                to_date=to_date,
                interval="day"
            )
            if not candles:
                return None
            result = scanner.scan(
                symbol=symbol,
                candles=candles
            )
            result["current_price"] = candles[-1]["close"]
            return result
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(scan_symbol, s)
            for s in watchlist
        ]
        done = 0
        for future in as_completed(futures):
            r = future.result()
            done += 1
            if r:
                results.append(r)
            if done % 100 == 0:
                print(f"  {done}/{len(watchlist)}...")

    results = sorted(
        results,
        key=lambda x: x["score"],
        reverse=True
    )

    if scan_type == "closing":
        await send_message(
            bot,
            "🌆 Closing scan — reviewing open positions only."
        )
        return

    strong = [
        r for r in results
        if r["tier"] == "STRONG"
        and r["symbol"] not in sent_today
    ]

    if not strong:
        await send_message(
            bot,
            f"{label} scan done. No new STRONG setups."
        )
        return

    await send_message(
        bot,
        f"🤖 AI analysing {len(strong)} setup(s)..."
    )

    analysed = analyse_setups(strong)

    if not analysed:
        await send_message(
            bot,
            "🤖 AI found no high-confidence setups this scan."
        )
        return

    costs = get_cost_summary()

    await send_message(
        bot,
        f"{label} scan done.\n"
        f"{len(analysed)} setup(s) passed AI review.\n"
        f"AI calls today: {costs['today_calls']}"
    )

    for setup in analysed:
        pending_setups[setup["symbol"]] = setup
        sent_today.add(setup["symbol"])
        await send_setup(bot, setup)


async def run_eod_summary(bot):
    from src.memory.trade_repository import (
        get_open_trades,
        get_closed_trades
    )

    open_trades = get_open_trades()
    closed_today = [
        t for t in get_closed_trades()
        if t.exit_time and
        t.exit_time.date() == datetime.utcnow().date()
    ]

    total_pnl = sum(
        t.pnl for t in closed_today if t.pnl
    )

    costs = get_cost_summary()

    await send_message(
        bot,
        f"📋 *End of Day Summary*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Open trades:    {len(open_trades)}\n"
        f"Closed today:   {len(closed_today)}\n"
        f"Today P&L:      ₹{total_pnl:,.0f}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"AI calls today: {costs['today_calls']}\n"
        f"AI calls month: {costs['month_calls']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Bot shutting down. See you tomorrow 🌙"
    )


async def scheduler(application):
    global sent_today
    fired = set()

    while True:
        now = datetime.now()
        key = now.strftime("%H:%M")

        if key == "00:00" and "reset" not in fired:
            sent_today.clear()
            fired.clear()
            fired.add("reset")

        if key == "08:45" and "morning" not in fired:
            fired.add("morning")
            await run_scan(application, "morning")

        elif key == "12:00" and "midday" not in fired:
            fired.add("midday")
            await run_scan(application, "midday")

        elif key == "15:00" and "closing" not in fired:
            fired.add("closing")
            await run_scan(application, "closing")

        elif key == "15:30" and "eod" not in fired:
            fired.add("eod")
            await run_eod_summary(application.bot)

        await asyncio.sleep(30)


async def post_init(application: Application):
    from src.monitor.position_monitor import run_monitor

    asyncio.create_task(scheduler(application))

    asyncio.create_task(
        run_monitor(application.bot, token_map)
    )

    await run_scan(application, "morning")


def main():
    app = (
        Application
        .builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(
        CallbackQueryHandler(handle_decision)
    )

    register_commands(app)

    print("Bot running. Market hours: 9:15 AM - 3:30 PM IST")
    print("Commands: /status /portfolio /close /pause /resume")

    app.run_polling()


if __name__ == "__main__":
    main()
