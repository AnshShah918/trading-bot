from src.utils.cost_calculator import (
    calculate_trade_costs
)

result = calculate_trade_costs(
    buy_value=15000,
    sell_value=16100,
    gross_pnl=1100
)

print(result)
