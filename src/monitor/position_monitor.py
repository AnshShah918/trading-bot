import os
import asyncio
from datetime import datetime, timedelta
from kiteconnect import KiteConnect
from dotenv import load_dotenv

from src.memory.trade_repository import (
    get_open_trades,
    close_trade,
    update_trade_stop,
    update_last_price
)
from src.portfolio.risk_manager import RiskManager
from src.portfolio.portfolio_manager import PortfolioManager
from src.indicators.market_indicators import MarketIndicators
from src.utils.cost_calculator import calculate_trade_costs
from src.utils.trading_calendar import is_t1_ready
from src.config.settings import (
    NIFTY_CIRCUIT_BREAKER_PCT,
    MONITOR_INTERVAL_MARKET,
    MONITOR_INTERVAL_OUTSIDE,
    MODE
)

load_dotenv()

portfolio = PortfolioManager()

MIN_PROFIT_RS = 1500
MIN_PROFIT_PCT = 8.0
NIFTY_TOKEN = 256265

_token_map = {}


def get_kite():
    kite = KiteConnect(
        api_key=os.getenv("KITE_API_KEY")
    )
    kite.set_access_token(
        os.getenv("KITE_ACCESS_TOKEN")
    )
    return kite


def ensure_token_map(kite, token_map_ref):
    if not token_map_ref:
        from src.universe.instrument_lookup import (
            InstrumentLookup
        )
        instruments = kite.instruments("NSE")
        built = InstrumentLookup.build_map(instruments)
        _token_map.update(built)
        return _token_map
    return token_map_ref


def get_live_price(kite, symbol):
    # Uses quote API — reflects current market price
    # not yesterday's close
    try:
        quote = kite.quote(f"NSE:{symbol}")
        return quote[f"NSE:{symbol}"]["last_price"]
    except Exception as e:
        print(f"Quote error {symbol}: {e}")
        return None


def get_candles_for_indicators(kite, token):
    # Still need candles for ATR and trend check
    # but NOT for current price
    try:
        to_date = datetime.now()
        from_date = to_date - timedelta(days=60)

        return kite.historical_data(
            instrument_token=token,
            from_date=from_date,
            to_date=to_date,
            interval="day"
        )
    except Exception as e:
        print(f"Candle fetch error: {e}")
        return []


def place_sell_order(kite, symbol, quantity):
    try:
        order_id = kite.place_order(
            variety=kite.VARIETY_REGULAR,
            exchange=kite.EXCHANGE_NSE,
            tradingsymbol=symbol,
            transaction_type=kite.TRANSACTION_TYPE_SELL,
            quantity=quantity,
            product=kite.PRODUCT_CNC,
            order_type=kite.ORDER_TYPE_MARKET
        )
        return order_id, None
    except Exception as e:
        return None, str(e)


def check_trend(candles):
    ma20 = MarketIndicators.moving_average(candles, 20)
    ma50 = MarketIndicators.moving_average(candles, 50)
    rsi = MarketIndicators.rsi(candles)
    current = candles[-1]["close"]
    return current > ma20 > ma50 and rsi < 70


def check_nifty_circuit(kite):
    try:
        quote = kite.quote("NSE:NIFTY 50")
        data = quote.get("NSE:NIFTY 50", {})

        current = data.get("last_price", 0)
        prev_close = data.get("ohlc", {}).get("close", 0)

        if not prev_close:
            return False, 0.0

        change_pct = (
            (current - prev_close)
            / prev_close * 100
        )

        return (
            change_pct <= -NIFTY_CIRCUIT_BREAKER_PCT,
            round(change_pct, 2)
        )

    except Exception as e:
        print(f"Nifty circuit check error: {e}")
        return False, 0.0


async def refresh_open_positions(bot, token_map):
    trades = get_open_trades()

    if not trades:
        await bot.send_message(
            chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            text="📭 No open positions to refresh."
        )
        return

    kite = get_kite()
    active_map = ensure_token_map(kite, token_map)

    lines = ["🔄 *Positions Refreshed*\n━━━━━━━━━━━━━━━━━━"]

    total_unrealised = 0

    for trade in trades:

        # Use live quote price
        live_price = get_live_price(kite, trade.symbol)

        price = (
            live_price
            or trade.last_known_price
            or trade.entry_price
        )

        if live_price:
            update_last_price(trade.id, live_price)

        unrealised = (
            (price - trade.entry_price)
            * trade.quantity
        )
        unrealised_pct = (
            (price - trade.entry_price)
            / trade.entry_price * 100
        )

        total_unrealised += unrealised
        emoji = "📈" if unrealised >= 0 else "📉"

        price_note = (
            "live" if live_price else "last known"
        )

        lines.append(
            f"\n*#{trade.id} {trade.symbol}*\n"
            f"Entry:  ₹{trade.entry_price}\n"
            f"Now:    ₹{price} ({price_note})\n"
            f"P&L:    {emoji} "
            f"₹{round(unrealised, 0):,.0f} "
            f"({round(unrealised_pct, 2)}%)\n"
            f"Stop:   ₹{round(trade.current_stop, 2) if trade.current_stop else 'N/A'}"
        )

    total_emoji = "📈" if total_unrealised >= 0 else "📉"
    lines.append(
        f"\n━━━━━━━━━━━━━━━━━━\n"
        f"Total: {total_emoji} "
        f"₹{round(total_unrealised, 0):,.0f}"
    )

    await bot.send_message(
        chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        text="\n".join(lines),
        parse_mode="Markdown"
    )


async def monitor_once(bot, token_map):

    trades = get_open_trades()

    if not trades:
        return

    kite = get_kite()
    active_map = ensure_token_map(kite, token_map)

    # Use live quote for Nifty circuit check
    circuit_hit, nifty_change = (
        check_nifty_circuit(kite)
    )

    if circuit_hit:
        await bot.send_message(
            chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            text=(
                f"🚨 *MARKET ALERT*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Nifty 50: {nifty_change}%\n"
                f"Circuit breaker triggered!\n"
                f"Stops tightened on all positions.\n"
                f"Consider /pause for new trades."
            ),
            parse_mode="Markdown"
        )

    for trade in trades:

        token = active_map.get(trade.symbol)

        if not token:
            continue

        try:

            # Live price via quote — catches intraday moves
            current_price = get_live_price(
                kite, trade.symbol
            )

            if not current_price:
                continue

            # Update DB immediately
            update_last_price(trade.id, current_price)

            # Candles still needed for ATR + trend
            candles = get_candles_for_indicators(
                kite, token
            )

            if not candles:
                continue

            current_atr = MarketIndicators.atr(candles)

            rm = RiskManager(
                entry_price=trade.entry_price,
                atr=current_atr
            )

            if trade.highest_price and trade.current_stop:
                rm.restore(
                    highest_price=trade.highest_price,
                    current_stop=trade.current_stop
                )

            if circuit_hit:
                rm.ATR_MULTIPLIER = 1.0

            result = rm.update(
                current_price=current_price,
                current_atr=current_atr
            )

            update_trade_stop(
                trade_id=trade.id,
                current_stop=result["trailing_stop"],
                highest_price=result["highest_price"]
            )

            t1_ready = is_t1_ready(trade.entry_time)

            # STOP HIT
            if result["stop_hit"] and t1_ready:

                exit_price = current_price

                if MODE == "live":
                    # Place actual sell order
                    order_id, error = place_sell_order(
                        kite,
                        trade.symbol,
                        trade.quantity
                    )

                    if error:
                        await bot.send_message(
                            chat_id=os.getenv(
                                "TELEGRAM_CHAT_ID"
                            ),
                            text=(
                                f"🚨 *STOP HIT — SELL FAILED*\n"
                                f"━━━━━━━━━━━━━━━━━━\n"
                                f"{trade.symbol}\n"
                                f"Price: ₹{current_price}\n"
                                f"Stop:  ₹{result['trailing_stop']}\n"
                                f"Error: {error}\n"
                                f"⚠️ SELL MANUALLY ON ZERODHA NOW"
                            ),
                            parse_mode="Markdown"
                        )
                        continue

                    # Wait for fill
                    await asyncio.sleep(3)

                    await bot.send_message(
                        chat_id=os.getenv(
                            "TELEGRAM_CHAT_ID"
                        ),
                        text=(
                            f"🔴 *Stop Hit — Sell Placed*\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"{trade.symbol}\n"
                            f"Zerodha ID: {order_id}\n"
                            f"Price: ~₹{current_price}\n"
                            f"Check Zerodha to confirm fill."
                        ),
                        parse_mode="Markdown"
                    )

                closed = close_trade(
                    trade.id,
                    exit_price,
                    "stop_loss_hit"
                )

                costs = calculate_trade_costs(
                    trade.entry_price * trade.quantity,
                    exit_price * trade.quantity,
                    closed.pnl
                )

                portfolio.apply_trade_result(
                    costs["net_pnl"]
                )

                if MODE == "paper":
                    await bot.send_message(
                        chat_id=os.getenv(
                            "TELEGRAM_CHAT_ID"
                        ),
                        text=(
                            f"🔴 *Stop Hit — {trade.symbol}*\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"Exit:    ₹{exit_price}\n"
                            f"Entry:   ₹{trade.entry_price}\n"
                            f"Net P&L: ₹{costs['net_pnl']:,.0f}\n"
                            f"📝 Paper trade closed."
                        ),
                        parse_mode="Markdown"
                    )

                continue

            if not t1_ready:
                continue

            # PROFIT THRESHOLD
            profit_rs = (
                result["profit_rs"] * trade.quantity
            )
            profit_pct = result["profit_pct"]

            threshold_hit = (
                profit_rs >= MIN_PROFIT_RS
                or profit_pct >= MIN_PROFIT_PCT
            )

            if threshold_hit:

                trend_strong = check_trend(candles)

                if trend_strong:
                    await bot.send_message(
                        chat_id=os.getenv(
                            "TELEGRAM_CHAT_ID"
                        ),
                        text=(
                            f"📈 *{trade.symbol}* "
                            f"+{profit_pct}% "
                            f"(₹{profit_rs:,.0f})\n"
                            f"Trend intact — holding.\n"
                            f"Stop → ₹{result['trailing_stop']}"
                        ),
                        parse_mode="Markdown"
                    )

                else:

                    exit_price = current_price

                    if MODE == "live":
                        order_id, error = place_sell_order(
                            kite,
                            trade.symbol,
                            trade.quantity
                        )

                        if error:
                            await bot.send_message(
                                chat_id=os.getenv(
                                    "TELEGRAM_CHAT_ID"
                                ),
                                text=(
                                    f"🚨 *PROFIT SELL FAILED*\n"
                                    f"{trade.symbol}\n"
                                    f"Error: {error}\n"
                                    f"⚠️ SELL MANUALLY ON ZERODHA"
                                ),
                                parse_mode="Markdown"
                            )
                            continue

                        await bot.send_message(
                            chat_id=os.getenv(
                                "TELEGRAM_CHAT_ID"
                            ),
                            text=(
                                f"📤 *Profit Sell Placed*\n"
                                f"{trade.symbol}\n"
                                f"Zerodha ID: {order_id}\n"
                                f"Price: ~₹{current_price}"
                            ),
                            parse_mode="Markdown"
                        )

                    closed = close_trade(
                        trade.id,
                        exit_price,
                        "profit_trend_weakening"
                    )

                    costs = calculate_trade_costs(
                        trade.entry_price * trade.quantity,
                        exit_price * trade.quantity,
                        closed.pnl
                    )

                    portfolio.apply_trade_result(
                        costs["net_pnl"]
                    )

                    if MODE == "paper":
                        await bot.send_message(
                            chat_id=os.getenv(
                                "TELEGRAM_CHAT_ID"
                            ),
                            text=(
                                f"📤 *Profit Booked — "
                                f"{trade.symbol}*\n"
                                f"━━━━━━━━━━━━━━━━━━\n"
                                f"Exit:    ₹{exit_price}\n"
                                f"Net P&L: ₹{costs['net_pnl']:,.0f}\n"
                                f"Reason:  Trend weakening\n"
                                f"📝 Paper trade closed."
                            ),
                            parse_mode="Markdown"
                        )

        except Exception as e:
            print(f"Monitor error {trade.symbol}: {e}")
            continue


async def run_monitor(bot, token_map):

    while True:

        now = datetime.now()

        market_open = now.replace(
            hour=9, minute=15, second=0
        )
        market_close = now.replace(
            hour=15, minute=30, second=0
        )

        in_market_hours = (
            market_open <= now <= market_close
        )

        if in_market_hours:
            await monitor_once(bot, token_map)
            await asyncio.sleep(MONITOR_INTERVAL_MARKET)
        else:
            await asyncio.sleep(MONITOR_INTERVAL_OUTSIDE)
