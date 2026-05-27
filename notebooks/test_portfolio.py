from src.portfolio.portfolio_manager import PortfolioManager

pm = PortfolioManager()

print("Starting")
print(pm.current_capital)

print("\nLoss -8000")
print(pm.apply_trade_result(-8000))

print("\nLoss -7000")
print(pm.apply_trade_result(-7000))

print("\nPause?")
print(pm.portfolio_paused())

print("\nLoss -1000")
print(pm.apply_trade_result(-1000))

print("\nPause?")
print(pm.portfolio_paused())
