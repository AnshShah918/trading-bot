from src.memory.db import get_db
from src.memory.models import Trade


def open_trade(
    symbol,
    entry_price,
    quantity,
    entry_reason=""
):

    db = get_db()

    trade = Trade(
        symbol=symbol,
        entry_price=entry_price,
        quantity=quantity,
        status="open",
        entry_reason=entry_reason
    )

    db.add(trade)
    db.commit()
    db.refresh(trade)
    db.close()

    return trade


def close_trade(
    trade_id,
    exit_price,
    exit_reason=""
):

    db = get_db()

    trade = db.query(Trade).filter(
        Trade.id == trade_id
    ).first()

    if trade:

        trade.exit_price = exit_price

        trade.pnl = (
            exit_price - trade.entry_price
        ) * trade.quantity

        trade.status = "closed"
        trade.exit_reason = exit_reason

        db.commit()
        db.refresh(trade)

    db.close()

    return trade


def get_open_trades():

    db = get_db()

    trades = db.query(Trade).filter(
        Trade.status == "open"
    ).all()

    db.close()

    return trades


def get_all_trades():

    db = get_db()

    trades = db.query(Trade).all()

    db.close()

    return trades
