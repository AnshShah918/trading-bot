from datetime import datetime
from src.memory.db import get_db
from src.memory.models import Trade


def open_trade(
    symbol,
    entry_price,
    quantity,
    entry_reason="",
    current_stop=None
):
    db = get_db()

    trade = Trade(
        symbol=symbol,
        entry_price=entry_price,
        quantity=quantity,
        status="open",
        entry_reason=entry_reason,
        entry_time=datetime.utcnow(),
        current_stop=current_stop,
        highest_price=entry_price
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
        trade.exit_time = datetime.utcnow()

        trade.pnl = (
            exit_price - trade.entry_price
        ) * trade.quantity

        trade.status = "closed"
        trade.exit_reason = exit_reason

        db.commit()
        db.refresh(trade)

    db.close()

    return trade


def update_trade_stop(
    trade_id,
    current_stop,
    highest_price
):
    db = get_db()

    trade = db.query(Trade).filter(
        Trade.id == trade_id
    ).first()

    if trade:
        trade.current_stop = current_stop
        trade.highest_price = highest_price
        db.commit()

    db.close()


def get_open_trades():
    db = get_db()
    trades = db.query(Trade).filter(
        Trade.status == "open"
    ).all()
    db.close()
    return trades


def get_closed_trades():
    db = get_db()
    trades = db.query(Trade).filter(
        Trade.status == "closed"
    ).all()
    db.close()
    return trades


def get_all_trades():
    db = get_db()
    trades = db.query(Trade).all()
    db.close()
    return trades
