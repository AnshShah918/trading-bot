from src.memory.trade_repository import (
    save_trade,
    get_all_trades
)

save_trade(
    symbol="TEST",
    entry_price=100,
    exit_price=110,
    quantity=10,
    pnl=100,
    status="closed",
    entry_reason="breakout",
    exit_reason="trailing_stop"
)

trades = get_all_trades()

for trade in trades:
    print(
        trade.id,
        trade.symbol,
        trade.pnl,
        trade.status
    )
