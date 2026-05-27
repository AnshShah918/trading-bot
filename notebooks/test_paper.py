from src.paper_trading.paper_engine import PaperEngine

engine = PaperEngine()

print("Starting Capital")
print(
    engine.portfolio.current_capital
)

trade = engine.open_position(
    symbol="INFY",
    entry_price=1500,
    quantity=10,
    entry_reason="breakout"
)

r1 = engine.update_position(
    trade.id,
    current_value=17000,
    close_confirmed=True
)

print("\nStop Update")
print(r1)

r2 = engine.update_position(
    trade.id,
    current_value=16100,
    close_confirmed=True
)

print("\nExit Signal")
print(r2)

if r2["stop_hit"]:

    result = engine.close_position(
        trade.id,
        exit_price=1610,
        exit_reason="closing_stop"
    )

    print("\nClosed Trade")
    print(
        result["trade"].symbol,
        result["trade"].pnl
    )

    print("\nPortfolio")
    print(
        result["portfolio"]
    )
