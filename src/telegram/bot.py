import os
import asyncio
from datetime import timezone, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes
)

from src.telegram.notifier import send_setup, send_message
from src.telegram.commands import register_commands
from src.paper_trading.paper_engine import PaperEngine
from src.ai.analyser import analyse_setups, get_cost_summary
from src.utils.trading_calendar import is_trading_day
from src.config.settings import (
    MAX_OPEN_TRADES,
    MIN_VIABLE_TRADE,
    RESERVE_PERCENT,
    TOP_N_TO_AI,
    MAX_AI_PICKS,
    TEST_MODE,
    MORNING_SCAN_TIME,
    MIDDAY_SCAN_TIME,
    CLOSING_SCAN_TIME,
    EOD_TIME,
    MODE
)

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")

paper = PaperEngine()
pending_setups = {}
sent_today = set()
token_map = {}
fired_today = set()


def get_capital_status():
    from src.memory.trade_repository import get_open_trades

    open_trades = get_open_trades()

    deployed = sum(
        t.entry_price * t.quantity
        for t in open_trades
    )

    total = paper.portfolio.current_capital
    reserve = total * RESERVE_PERCENT
    available = max(0, total - deployed - reserve)

    return {
        "total": total,
        "deployed": deployed,
        "reserve": reserve,
        "available": available,
        "open_count": len(open_trades)
    }


def get_live_price(kite, symbol):
    try:
        quote = kite.quote(f"NSE:{symbol}")
        return quote[f"NSE:{symbol}"]["last_price"]
    except Exception:
        return None


def verify_zerodha_order(kite, order_id):
    try:
        orders = kite.orders()
        for order in orders:
            if str(order["order_id"]) == str(order_id):
                return {
                    "status": order["status"],
                    "filled_qty": order.get(
                        "filled_quantity", 0
                    ),
                    "avg_price": order.get(
                        "average_price", 0
                    )
                }
        return None
    except Exception as e:
        print(f"Order verify error: {e}")
        return None


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

        cap = get_capital_status()

        if cap["open_count"] >= MAX_OPEN_TRADES:
            await query.edit_message_text(
                f"❌ Max trades ({MAX_OPEN_TRADES}) "
                f"already open."
            )
            return

        if cap["available"] < MIN_VIABLE_TRADE:
            await query.edit_message_text(
                f"❌ Insufficient capital.\n"
                f"Available: ₹{cap['available']:,.0f}\n"
                f"Reserve locked: ₹{cap['reserve']:,.0f}"
            )
            return

        now = datetime.now().strftime("%d %b %H:%M")

        if MODE == "live":
            from kiteconnect import KiteConnect
            kite = KiteConnect(
                api_key=os.getenv("KITE_API_KEY")
            )
            kite.set_access_token(
                os.getenv("KITE_ACCESS_TOKEN")
            )

            try:
                order_id = kite.place_order(
                    variety=kite.VARIETY_REGULAR,
                    exchange=kite.EXCHANGE_NSE,
                    tradingsymbol=symbol,
                    transaction_type=(
                        kite.TRANSACTION_TYPE_BUY
                    ),
                    quantity=setup["shares_to_buy"],
                    product=kite.PRODUCT_CNC,
                    order_type=kite.ORDER_TYPE_MARKET
                )

                await asyncio.sleep(3)

                verified = verify_zerodha_order(
                    kite, order_id
                )

                if (
                    verified
                    and verified["status"] == "COMPLETE"
                ):
                    actual_price = verified["avg_price"]
                    actual_qty = verified["filled_qty"]

                    trade = paper.open_position(
                        symbol=symbol,
                        entry_price=actual_price,
                        quantity=actual_qty,
                        entry_reason=(
                            f"score={setup['score']} "
                            f"rsi={setup['rsi']} "
                            f"order_id={order_id}"
                        ),
                        atr=setup["atr"],
                        current_stop=setup["suggested_stop"]
                    )

                    await query.edit_message_text(
                        f"✅ *LIVE ORDER CONFIRMED*\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"#{trade.id} {symbol}\n"
                        f"Zerodha ID: {order_id}\n"
                        f"Status:  COMPLETE ✅\n"
                        f"Entry:   ₹{actual_price}\n"
                        f"Shares:  {actual_qty}\n"
                        f"Target:  ₹{setup['target_price']}\n"
                        f"Stop:    ₹{setup['suggested_stop']}\n"
                        f"Placed:  {now}",
                        parse_mode="Markdown"
                    )

                elif verified:
                    await query.edit_message_text(
                        f"⚠️ *ORDER PLACED — NOT FILLED*\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"{symbol}\n"
                        f"Zerodha ID: {order_id}\n"
                        f"Status: {verified['status']}\n"
                        f"Check Zerodha app to confirm.\n"
                        f"Placed: {now}",
                        parse_mode="Markdown"
                    )

                else:
                    await query.edit_message_text(
                        f"⚠️ *VERIFY MANUALLY*\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"{symbol}\n"
                        f"Zerodha ID: {order_id}\n"
                        f"Could not confirm status.\n"
                        f"Check Zerodha app now.\n"
                        f"Placed: {now}",
                        parse_mode="Markdown"
                    )

            except Exception as e:
                await query.edit_message_text(
                    f"❌ *ORDER FAILED*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"{symbol}\n"
                    f"Error: {str(e)}\n"
                    f"Nothing placed on Zerodha."
                )
                return

        else:
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
                f"📝 *PAPER TRADE LOGGED*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"#{trade.id} {symbol}\n"
                f"Entry:   ₹{setup['current_price']}\n"
                f"Target:  ₹{setup['target_price']}\n"
                f"Stop:    ₹{setup['suggested_stop']}\n"
                f"Shares:  {setup['shares_to_buy']}\n"
                f"Capital: ₹{setup['trade_value']}\n"
                f"Logged:  {now}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ No real order placed.",
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

    if not is_trading_day() and not TEST_MODE:
        await send_message(
            bot,
            "📅 Market closed today — no scan.\n"
            "Use /scan to force one."
        )
        return

    cap = get_capital_status()

    if cap["open_count"] >= MAX_OPEN_TRADES:
        await send_message(
            bot,
            f"📊 Scan skipped — max trades open "
            f"({cap['open_count']}/{MAX_OPEN_TRADES})."
        )
        return

    if cap["available"] < MIN_VIABLE_TRADE:
        await send_message(
            bot,
            f"💰 Scan skipped — "
            f"available ₹{cap['available']:,.0f} "
            f"below minimum."
        )
        return

    label = {
        "morning": "🌅 Morning",
        "midday": "☀️ Mid-day",
        "closing": "🌆 Closing",
        "manual": "🔍 Manual"
    }.get(scan_type, "")

    await send_message(
        bot,
        f"{label} scan starting...\n"
        f"Available: ₹{cap['available']:,.0f} "
        f"(₹{cap['reserve']:,.0f} reserved)\n"
        f"Trades: {cap['open_count']}/{MAX_OPEN_TRADES}"
    )

    kite = KiteConnect(
        api_key=os.getenv("KITE_API_KEY")
    )
    kite.set_access_token(
        os.getenv("KITE_ACCESS_TOKEN")
    )

    instruments = kite.instruments("NSE")
    token_map = InstrumentLookup.build_map(instruments)
    application.bot_data["token_map"] = token_map
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
                candles=candles,
                available_capital=cap["available"]
            )

            live_price = get_live_price(kite, symbol)

            result["current_price"] = (
                live_price
                if live_price
                else candles[-1]["close"]
            )

            if live_price:
                atr = result["atr"]
                stop = round(
                    live_price - (atr * 1.5), 2
                )
                risk = live_price - stop
                target = round(
                    live_price + (risk * 2), 2
                )
                result["suggested_stop"] = stop
                result["target_price"] = target
                result["risk_pct"] = round(
                    risk / live_price * 100, 2
                )
                result["target_pct"] = round(
                    (target - live_price)
                    / live_price * 100, 2
                )
                result["risk_per_share"] = round(
                    risk, 2
                )
                if cap["available"] > 0:
                    pos_capital = (
                        cap["available"] * 0.25
                    )
                    result["shares_to_buy"] = int(
                        pos_capital / live_price
                    )
                    result["trade_value"] = round(
                        result["shares_to_buy"]
                        * live_price, 2
                    )

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
            "🌆 Closing scan — reviewing open positions."
        )
        return

    slots = MAX_OPEN_TRADES - cap["open_count"]

    strong = [
        r for r in results
        if r["tier"] == "STRONG"
        and r["symbol"] not in sent_today
    ]

    if not strong:
        best = (
            max(results, key=lambda x: x["score"])
            if results else None
        )
        best_note = (
            f"Best score: {best['score']} "
            f"({best['symbol']})"
            if best else ""
        )
        await send_message(
            bot,
            f"{label} scan done.\n"
            f"❌ Scanner: No STRONG setups.\n"
            f"{best_note}"
        )
        return

    top_n = strong[:TOP_N_TO_AI]

    await send_message(
        bot,
        f"🤖 AI reviewing {len(top_n)} setups "
        f"(max {min(MAX_AI_PICKS, slots)} picks)..."
    )

    analysed = analyse_setups(
        setups=top_n,
        available_capital=cap["available"],
        max_picks=min(MAX_AI_PICKS, slots)
    )

    if not analysed:
        symbols = [s["symbol"] for s in top_n]
        await send_message(
            bot,
            f"🤖 AI reviewed: {', '.join(symbols)}\n"
            f"❌ AI: None met conviction threshold.\n"
            f"Scanner: {len(strong)} STRONG found\n"
            f"but AI rejected all."
        )
        return

    costs = get_cost_summary()

    await send_message(
        bot,
        f"{label} done — "
        f"{len(analysed)} setup(s) selected.\n"
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
        if t.exit_time
        and t.exit_time.date() ==
        datetime.now(timezone.utc).date()
    ]

    total_pnl = sum(
        t.pnl for t in closed_today if t.pnl
    )

    total_unrealised = sum(
        (
            (t.last_known_price or t.entry_price)
            - t.entry_price
        ) * t.quantity
        for t in open_trades
    )

    costs = get_cost_summary()
    cap = get_capital_status()

    await send_message(
        bot,
        f"📋 *End of Day Summary*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Open trades:      {len(open_trades)}\n"
        f"Closed today:     {len(closed_today)}\n"
        f"Realised P&L:     ₹{total_pnl:,.0f}\n"
        f"Unrealised P&L:   "
        f"₹{round(total_unrealised, 0):,.0f}\n"
        f"Available:        ₹{cap['available']:,.0f}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"AI calls today:   {costs['today_calls']}\n"
        f"AI calls month:   {costs['month_calls']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Bot shutting down. See you tomorrow 🌙"
    )


async def cmd_scan(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if context.bot_data.get("paused"):
        await update.message.reply_text(
            "⏸ Bot is paused. Send /resume first."
        )
        return

    await update.message.reply_text(
        "🔍 Manual scan triggered..."
    )

    await run_scan(context.application, "manual")


async def scheduler(application):
    global sent_today, fired_today

    while True:

        now = datetime.now()
        today = now.date().isoformat()
        key = now.strftime("%H:%M")

        if today not in fired_today:
            sent_today.clear()
            fired_today.clear()
            fired_today.add(today)

        if (
            key == MORNING_SCAN_TIME
            and "morning" not in fired_today
        ):
            fired_today.add("morning")
            await run_scan(application, "morning")

        elif (
            key == MIDDAY_SCAN_TIME
            and "midday" not in fired_today
        ):
            fired_today.add("midday")
            await run_scan(application, "midday")

        elif (
            key == CLOSING_SCAN_TIME
            and "closing" not in fired_today
        ):
            fired_today.add("closing")
            await run_scan(application, "closing")

        elif (
            key == EOD_TIME
            and "eod" not in fired_today
        ):
            fired_today.add("eod")
            await run_eod_summary(application.bot)

        await asyncio.sleep(30)


async def post_init(application: Application):
    from src.monitor.position_monitor import run_monitor

    asyncio.create_task(scheduler(application))
    asyncio.create_task(
        run_monitor(application.bot, token_map)
    )

    now = datetime.now()
    hour = now.hour
    minute = now.minute

    if not is_trading_day() and not TEST_MODE:
        await send_message(
            application.bot,
            "📅 Market closed today.\n"
            "Monitoring open positions only.\n"
            "Use /status to check positions.\n"
            "Use /scan to force a scan."
        )
        return

    if hour < 9 or (hour == 9 and minute < 20):
        await send_message(
            application.bot,
            f"🤖 Bot ready.\n"
            f"Morning scan fires at "
            f"{MORNING_SCAN_TIME}\n"
            f"Or use /scan to run now."
        )

    elif hour < 12:
        fired_today.add("morning")
        await run_scan(application, "morning")

    elif hour < 15:
        fired_today.add("morning")
        fired_today.add("midday")
        await run_scan(application, "midday")

    else:
        fired_today.add("morning")
        fired_today.add("midday")
        fired_today.add("closing")
        await send_message(
            application.bot,
            f"🌆 Started after market hours.\n"
            f"Monitoring open positions.\n"
            f"Next scan tomorrow at "
            f"{MORNING_SCAN_TIME}.\n"
            f"Use /status to check positions."
        )


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

    app.add_handler(
        CommandHandler("scan", cmd_scan)
    )

    register_commands(app)

    mode_label = (
        "🔴 LIVE TRADING"
        if MODE == "live"
        else "📝 PAPER TRADING"
    )

    print(f"Bot running — {mode_label}")
    print(
        f"Scans: {MORNING_SCAN_TIME} | "
        f"{MIDDAY_SCAN_TIME} | "
        f"{CLOSING_SCAN_TIME} IST"
    )
    print(
        "Commands: /help /scan /status "
        "/portfolio /close /pause /resume"
    )

    app.run_polling()


if __name__ == "__main__":
    main()
