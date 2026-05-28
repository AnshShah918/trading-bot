import os
import asyncio
from datetime import datetime, timedelta
from kiteconnect import KiteConnect
from dotenv import load_dotenv

from src.memory.trade_repository import (
    get_open_trades,
    close_trade,
    update_trade_stop
)
from src.portfolio.risk_manager import RiskManager
from src.portfolio.portfolio_manager import PortfolioManager
from src.indicators.market_indicators import MarketIndicators
from src.utils.cost_calculator import calculate_trade_costs
from src.utils.trading_calendar import is_t1_ready
from src.config.settings import (
    NIFTY_CIRCUIT_BREAKER_PCT,
    MONITOR_INTERVAL_MARKET,
    MONITOR_INTERVAL_OUTSIDE
)

load_dotenv()

portfolio = PortfolioManager()

MIN_PROFIT_RS = 1500
MIN_PROFIT_PCT = 8.0

NIFTY_TOKEN = 256265  # NSE:NIFTY 50


def get_kite():
    kite = KiteConnect(
        api_key=os.getenv("KITE_API_KEY")
    )
    kite.set_access_token(
        os.getenv("KITE_ACCESS_TOKEN")
    )
    return kite


def check_trend(candles):
    ma20 = MarketIndicators.moving_average(candles, 20)
    ma50 = MarketIndicators.moving_average(candles, 50)
    rsi = MarketIndicators.rsi(candles)
    current = candles[-1]["close"]

    return (
        current > ma20 > ma50
        and rsi < 70
    )


def check_nifty_circuit(kite):
    try:
        to_date = datetime.now()
        from_date = to_date - timedelta(days=5)

        candles = kite.historical_data(
            instrument_token=NIFTY_TOKEN,
            from_date=from_date,
            to_date=to_date,
            interval="day"
        )

        if len(candles) < 2:
            return False, 0.0

        prev_close = candles[-2]["close"]
        current = candles[-1]["close"]

        change_pct = (
            (current - prev_close)
            / prev_close * 100
        )

        circuit_hit = (
            change_pct <= -NIFTY_CIRCUIT_BREAKER_PCT
        )

        return circuit_hit, round(change_pct, 2)

    except Exception as e:
        print(f"Nifty circuit check error: {e}")
        return False, 0.0


async def monitor_once(bot, token_map):

    trades = get_open_trades()

    if not trades:
        return

    kite = get_kite()

    # Check Nifty first
    circuit_hit, nifty_change = check_nifty_circuit(kite)

    if circuit_hit:
        await bot.send_message(
            chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            text=(
                f"🚨 *MARKET ALERT*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Nifty 50: {nifty_change}%\n"
                f"Circuit breaker triggered!\n"
                f"Tightening all stop losses.\n"
                f"Consider /pause to stop new trades."
            ),
            parse_mode="Markdown"
        )

    for trade in trades:

        token = token_map.get(trade.symbol)

        if not token:
            continue

        try:

            to_date = datetime.now()
            from_date = to_date - timedelta(days=60)

            candles = kite.historical_data(
                instrument_token=token,
                from_date=from_date,
                to_date=to_date,
                interval="day"
            )

            if not candles:
                continue

            current_price = candles[-1]["close"]
            current_atr = MarketIndicators.atr(candles)

            # Tighten stop if circuit hit
            atr_multiplier = (
                1.0 if circuit_hit else 1.5
            )

            rm = RiskManager(
                entry_price=trade.entry_price,
                atr=current_atr
            )

            if trade.highest_price and trade.current_stop:
                rm.restore(
                    highest_price=trade.highest_price,
                    current_stop=trade.current_stop
                )

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

                closed = close_trade(
                    trade.id,
                    current_price,
                    "stop_loss_hit"
                )

                costs = calculate_trade_costs(
                    trade.entry_price * trade.quantity,
                    current_price * trade.quantity,
                    closed.pnl
                )

                portfolio.apply_trade_result(
                    costs["net_pnl"]
                )

                await bot.send_message(
                    chat_id=os.getenv("TELEGRAM_CHAT_ID"),
                    text=(
                        f"🔴 *Stop Hit — {trade.symbol}*\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"Exit:    ₹{current_price}\n"
                        f"Entry:   ₹{trade.entry_price}\n"
                        f"Net P&L: ₹{costs['net_pnl']:,.0f}\n"
                        f"Trade #{trade.id} closed."
                    ),
                    parse_mode="Markdown"
                )

                continue

            # T+1 not ready yet
            if not t1_ready:
                continue

            # PROFIT THRESHOLD
            profit_rs = result["profit_rs"] * trade.quantity
            profit_pct = result["profit_pct"]

            threshold_hit = (
                profit_rs >= MIN_PROFIT_RS
                or profit_pct >= MIN_PROFIT_PCT
            )

            if threshold_hit:

                trend_strong = check_trend(candles)

                if trend_strong:
                    await bot.send_message(
                        chat_id=os.getenv("TELEGRAM_CHAT_ID"),
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

                    closed = close_trade(
                        trade.id,
                        current_price,
                        "profit_trend_weakening"
                    )

                    costs = calculate_trade_costs(
                        trade.entry_price * trade.quantity,
                        current_price * trade.quantity,
                        closed.pnl
                    )

                    portfolio.apply_trade_result(
                        costs["net_pnl"]
                    )

                    await bot.send_message(
                        chat_id=os.getenv("TELEGRAM_CHAT_ID"),
                        text=(
                            f"📤 *Profit Booked — "
                            f"{trade.symbol}*\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"Exit:    ₹{current_price}\n"
                            f"Net P&L: ₹{costs['net_pnl']:,.0f}\n"
                            f"Reason:  Trend weakening\n"
                            f"Trade #{trade.id} closed."
                        ),
                        parse_mode="Markdown"
                    )

        except Exception as e:
            print(
                f"Monitor error {trade.symbol}: {e}"
            )
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
            await asyncio.sleep(
                MONITOR_INTERVAL_MARKET  # 5 mins
            )
        else:
            await asyncio.sleep(
                MONITOR_INTERVAL_OUTSIDE  # 30 mins
            )
