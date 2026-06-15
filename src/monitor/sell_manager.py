import os
import asyncio
from datetime import datetime
from kiteconnect import KiteConnect
from dotenv import load_dotenv
from src.portfolio.portfolio_manager import PortfolioManager

load_dotenv()

MAX_REPRICE_ATTEMPTS = 3
REPRICE_WAIT_SECONDS = 30

# Sells queued for next market open
# {trade_id: {symbol, quantity, reason}}
_queued_sells = {}
portfolio = PortfolioManager()


def get_kite():
    kite = KiteConnect(
        api_key=os.getenv("KITE_API_KEY")
    )
    kite.set_access_token(
        os.getenv("KITE_ACCESS_TOKEN")
    )
    return kite


def is_market_open():
    now = datetime.now()
    market_open = now.replace(
        hour=9, minute=15, second=0
    )
    market_close = now.replace(
        hour=15, minute=30, second=0
    )
    from src.utils.trading_calendar import is_trading_day
    return (
        is_trading_day()
        and market_open <= now <= market_close
    )


def get_current_bid(kite, symbol):
    try:
        quote = kite.quote(f"NSE:{symbol}")
        data = quote.get(f"NSE:{symbol}", {})

        depth = data.get("depth", {})
        bids = depth.get("buy", [])

        # Best bid — highest price buyer willing to pay
        if bids:
            return bids[0].get("price", 0)

        return data.get("last_price", 0)

    except Exception as e:
        print(f"Bid fetch error {symbol}: {e}")
        return None


def is_lower_circuit(kite, symbol):
    try:
        quote = kite.quote(f"NSE:{symbol}")
        data = quote.get(f"NSE:{symbol}", {})

        lower_circuit = data.get(
            "lower_circuit_limit", 0
        )
        last_price = data.get("last_price", 0)

        # Within 0.1% of lower circuit = effectively locked
        if lower_circuit and last_price:
            return (
                last_price <= lower_circuit * 1.001
            )

        return False

    except Exception:
        return False


def place_limit_sell(kite, symbol, quantity, price):
    try:
        order_id = kite.place_order(
            variety=kite.VARIETY_REGULAR,
            exchange=kite.EXCHANGE_NSE,
            tradingsymbol=symbol,
            transaction_type=(
                kite.TRANSACTION_TYPE_SELL
            ),
            quantity=quantity,
            product=kite.PRODUCT_CNC,
            order_type=kite.ORDER_TYPE_LIMIT,
            price=round(price, 2)
        )
        return order_id, None
    except Exception as e:
        return None, str(e)


def place_market_sell(kite, symbol, quantity):
    try:
        order_id = kite.place_order(
            variety=kite.VARIETY_REGULAR,
            exchange=kite.EXCHANGE_NSE,
            tradingsymbol=symbol,
            transaction_type=(
                kite.TRANSACTION_TYPE_SELL
            ),
            quantity=quantity,
            product=kite.PRODUCT_CNC,
            order_type=kite.ORDER_TYPE_MARKET
        )
        return order_id, None
    except Exception as e:
        return None, str(e)


def cancel_order(kite, order_id):
    try:
        kite.cancel_order(
            variety=kite.VARIETY_REGULAR,
            order_id=order_id
        )
        return True
    except Exception:
        return False


def check_order_status(kite, order_id):
    try:
        orders = kite.orders()
        for order in orders:
            if str(order["order_id"]) == str(order_id):
                return {
                    "status": order["status"],
                    "filled_qty": order.get(
                        "filled_quantity", 0
                    ),
                    "pending_qty": order.get(
                        "pending_quantity", 0
                    ),
                    "avg_price": order.get(
                        "average_price", 0
                    )
                }
        return None
    except Exception as e:
        print(f"Order status error: {e}")
        return None


async def execute_sell_with_failsafe(
    bot,
    trade,
    exit_reason,
    on_success,
    on_failure
):
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    kite = get_kite()
    symbol = trade.symbol
    quantity = trade.quantity

    # Market closed — queue for tomorrow
    if not is_market_open():
        _queued_sells[trade.id] = {
            "symbol": symbol,
            "quantity": quantity,
            "reason": exit_reason,
            "trade": trade
        }

        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"⚠️ *Market Closed — Sell Queued*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{symbol}\n"
                f"Stop loss triggered after hours.\n"
                f"Options:\n"
                f"1. Bot will attempt sell at 9:15 AM\n"
                f"   (risk: stock may gap down further)\n"
                f"2. You decide — /cancel_queue "
                f"{trade.id} to cancel\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ Review before market opens."
            ),
            parse_mode="Markdown"
        )
        return

    # Check lower circuit first
    if is_lower_circuit(kite, symbol):
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"🔒 *Lower Circuit — {symbol}*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Stock is at lower circuit limit.\n"
                f"No buyers available right now.\n"
                f"Bot will retry every 5 mins.\n"
                f"Or sell manually when circuit lifts.\n"
                f"Then run: /confirm {trade.id} <price>"
            ),
            parse_mode="Markdown"
        )
        # Queue for retry
        _queued_sells[trade.id] = {
            "symbol": symbol,
            "quantity": quantity,
            "reason": exit_reason,
            "trade": trade,
            "circuit": True
        }
        return

    # Try market sell first
    order_id, error = place_market_sell(
        kite, symbol, quantity
    )

    if error:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"⚠️ Market sell failed: {error}\n"
                f"Trying limit sell at bid price..."
            ),
            parse_mode="Markdown"
        )

        # Fall back to limit at current bid
        bid = get_current_bid(kite, symbol)
        if bid:
            order_id, error = place_limit_sell(
                kite, symbol, quantity, bid
            )

        if error or not order_id:
            await on_failure(
                f"Could not place any sell order.\n"
                f"Error: {error}\n"
                f"SELL MANUALLY ON ZERODHA.\n"
                f"Then: /confirm {trade.id} <price>"
            )
            return

    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"📤 Sell placed for {symbol}\n"
            f"Order: {order_id}\n"
            f"Monitoring fill..."
        ),
        parse_mode="Markdown"
    )

    # Monitor order with repricing
    remaining_qty = quantity

    for attempt in range(MAX_REPRICE_ATTEMPTS):

        await asyncio.sleep(REPRICE_WAIT_SECONDS)

        status = check_order_status(kite, order_id)

        if not status:
            continue

        if status["status"] == "COMPLETE":
            await on_success(
                order_id,
                status["avg_price"],
                status["filled_qty"]
            )
            return

        if status["status"] in (
            "REJECTED", "CANCELLED"
        ):
            # Order rejected — try repricing
            bid = get_current_bid(kite, symbol)

            if not bid:
                await on_failure(
                    f"Order {status['status']}.\n"
                    f"Could not get bid price.\n"
                    f"SELL MANUALLY.\n"
                    f"Then: /confirm {trade.id} <price>"
                )
                return

            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⚠️ Order {status['status']}.\n"
                    f"Repricing to ₹{bid} "
                    f"(attempt {attempt + 1}/"
                    f"{MAX_REPRICE_ATTEMPTS})..."
                ),
                parse_mode="Markdown"
            )

            order_id, error = place_limit_sell(
                kite, symbol, remaining_qty, bid
            )

            if error:
                await on_failure(
                    f"Reprice failed: {error}\n"
                    f"SELL MANUALLY.\n"
                    f"Then: /confirm {trade.id} <price>"
                )
                return

            continue

        if status["status"] == "OPEN":
            # Still pending — cancel and reprice
            filled = status.get("filled_qty", 0)
            remaining_qty = quantity - filled

            if filled > 0:
                # Partial fill — handle what's done
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"⚠️ Partial fill: "
                        f"{filled}/{quantity} shares.\n"
                        f"Cancelling and repricing "
                        f"remaining {remaining_qty}..."
                    ),
                    parse_mode="Markdown"
                )

            cancel_order(kite, order_id)

            await asyncio.sleep(2)

            bid = get_current_bid(kite, symbol)

            if not bid:
                await on_failure(
                    f"Could not get market price.\n"
                    f"SELL {remaining_qty} shares MANUALLY.\n"
                    f"Then: /confirm {trade.id} <price>"
                )
                return

            order_id, error = place_limit_sell(
                kite, symbol, remaining_qty, bid
            )

            if error:
                await on_failure(
                    f"Could not reprice order.\n"
                    f"SELL {remaining_qty} MANUALLY.\n"
                    f"Then: /confirm {trade.id} <price>"
                )
                return

            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"📤 Repriced to ₹{bid}\n"
                    f"New order: {order_id}"
                ),
                parse_mode="Markdown"
            )

    # All reprice attempts exhausted
    await on_failure(
        f"Could not fill after "
        f"{MAX_REPRICE_ATTEMPTS} attempts.\n"
        f"SELL MANUALLY ON ZERODHA.\n"
        f"Then: /confirm {trade.id} <exit_price>"
    )


async def process_queued_sells(bot):
    if not _queued_sells:
        return

    if not is_market_open():
        return

    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    kite = get_kite()

    for trade_id, queued in list(
        _queued_sells.items()
    ):
        symbol = queued["symbol"]

        # Check if still in circuit
        if queued.get("circuit"):
            if is_lower_circuit(kite, symbol):
                continue  # Still locked, skip

            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🔓 {symbol} circuit lifted.\n"
                    f"Attempting queued sell..."
                ),
                parse_mode="Markdown"
            )

        _queued_sells.pop(trade_id, None)

        trade = queued["trade"]

        async def on_success(order_id, price, qty):
            from src.memory.trade_repository import (
                close_trade,
                update_trade_net_pnl
            )
            from src.utils.cost_calculator import (
                calculate_trade_costs
            )

            closed = close_trade(
                trade_id, price, queued["reason"]
            )
            costs = calculate_trade_costs(
                trade.entry_price * trade.quantity,
                price * trade.quantity,
                closed.pnl
            )
            portfolio.apply_trade_result(
                costs["net_pnl"]
            )
            update_trade_net_pnl(
                closed.id,
                costs["net_pnl"]
            )
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"✅ Queued sell complete: "
                    f"{symbol}\n"
                    f"Exit: ₹{price}\n"
                    f"Net P&L: ₹{costs['net_pnl']:,.0f}"
                ),
                parse_mode="Markdown"
            )

        async def on_failure(msg):
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🚨 Queued sell failed: "
                    f"{symbol}\n{msg}"
                ),
                parse_mode="Markdown"
            )

        await execute_sell_with_failsafe(
            bot, trade,
            queued["reason"],
            on_success,
            on_failure
        )
