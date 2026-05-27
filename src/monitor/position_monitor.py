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
from src.universe.instrument_lookup import InstrumentLookup
from src.utils.cost_calculator import calculate_trade_costs

load_dotenv()

portfolio = PortfolioManager()

MIN_PROFIT_RS = 1500
MIN_PROFIT_PCT = 0.08


def get_kite():
    kite = KiteConnect(
        api_key=os.getenv("KITE_API_KEY")
    )
    kite.set_access_token(
        os.getenv("KITE_ACCESS_TOKEN")
    )
    return kite


def fetch_current_price_and_atr(
    kite,
    token,
    symbol
):
    to_date = datetime.now()
    from_date = to_date - timedelta(days=30)

    candles = kite.historical_data(
        instrument_token=token,
        from_date=from_date,
        to_date=to_date,
        interval="day"
    )

    if not candles:
        return None, None

    current_price = candles[-1]["close"]
    atr = MarketIndicators.atr(candles)

    return current_price, atr


def check_trend(candles):
    ma20 = MarketIndicators.moving_average(candles, 20)
    ma50 = MarketIndicators.moving_average(candles, 50)
    rsi = MarketIndicators.rsi(candles)
    current = candles[-1]["close"]

    trend_strong = (
        current > ma20 > ma50
        and rsi < 70
    )

    return trend_strong


async def monitor_once(bot, token_map):

    trades = get_open_trades()

    if not trades:
        return

    kite = get_kite()

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

            # Restore risk manager state from DB
            rm = RiskManager(
                entry_price=trade.entry_price,
                atr=current_atr
            )

            # Restore highest price from DB
            if trade.highest_price:
                rm.highest_price = trade.highest_price
                rm.trailing_stop = (
                    trade.current_stop
                    or rm.trailing_stop
                )

            result = rm.update(
                current_price=current_price,
                current_atr=current_atr
            )

            # Always update stop in DB
            update_trade_stop(
                trade_id=trade.id,
                current_stop=result["trailing_stop"],
                highest_price=result["highest_price"]
            )

            hold_days = (
                datetime.utcnow() - trade.entry_time
            ).days if trade.entry_time else 0

            t1_ready = hold_days >= 1

            # STOP HIT — auto exit
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
                        f"🔴 *Stop Loss Hit — {trade.symbol}*\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"Exit:      ₹{current_price}\n"
                        f"Entry:     ₹{trade.entry_price}\n"
                        f"Net P&L:   ₹{costs['net_pnl']:,.0f}\n"
                        f"Charges:   ₹{costs['charges']}\n"
                        f"Trade #{trade.id} closed."
                    ),
                    parse_mode="Markdown"
                )

                continue

            # PROFIT THRESHOLD — check trend
            profit_rs = result["profit_rs"] * trade.quantity
            profit_pct = result["profit_pct"]

            threshold_hit = (
                profit_rs >= MIN_PROFIT_RS
                or profit_pct >= MIN_PROFIT_PCT * 100
            )

            if threshold_hit and t1_ready:

                trend_strong = check_trend(candles)

                if trend_strong:
                    await bot.send_message(
                        chat_id=os.getenv("TELEGRAM_CHAT_ID"),
                        text=(
                            f"📈 *{trade.symbol}* +{profit_pct}%\n"
                            f"Trend intact — holding.\n"
                            f"Stop trailed to ₹{result['trailing_stop']}"
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
                            f"📤 *Profit Booked — {trade.symbol}*\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"Exit:      ₹{current_price}\n"
                            f"Net P&L:   ₹{costs['net_pnl']:,.0f}\n"
                            f"Reason:    Trend weakening at profit\n"
                            f"Trade #{trade.id} closed."
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

        if market_open <= now <= market_close:
            await monitor_once(bot, token_map)
            await asyncio.sleep(1800)  # 30 mins
        else:
            await asyncio.sleep(300)   # 5 mins outside hours
