from src.portfolio.risk_manager import RiskManager

rm = RiskManager(50000)

tests = [
    (50000, True),
    (55000, True),
    (60000, True),

    # Intraday dip below stop
    (56000, False),

    # Close below stop
    (56000, True)
]

for price, close_confirmed in tests:
    result = rm.update(price, close_confirmed)
    print(result)
