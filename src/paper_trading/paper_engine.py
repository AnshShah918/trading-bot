from src.memory.trade_repository import (
    open_trade,
    close_trade,
    update_trade_net_pnl
)
from src.portfolio.risk_manager import RiskManager
from src.portfolio.portfolio_manager import PortfolioManager
from src.utils.cost_calculator import calculate_trade_costs


class PaperEngine:

    def __init__(self):
        self.active_trades = {}
        self.portfolio = PortfolioManager()

    def open_position(
        self,
        symbol,
        entry_price,
        quantity,
        entry_reason,
        atr,
        current_stop=None,
        entry_snapshot=None
    ):
        trade = open_trade(
            symbol=symbol,
            entry_price=entry_price,
            quantity=quantity,
            entry_reason=entry_reason,
            current_stop=current_stop,
            entry_snapshot=entry_snapshot
        )

        rm = RiskManager(
            entry_price=entry_price,
            atr=atr
        )

        self.active_trades[trade.id] = rm

        return trade

    def close_position(
        self,
        trade_id,
        exit_price,
        exit_reason
    ):
        trade = close_trade(
            trade_id,
            exit_price,
            exit_reason
        )

        buy_value = (
            trade.entry_price * trade.quantity
        )

        sell_value = (
            trade.exit_price * trade.quantity
        )

        costs = calculate_trade_costs(
            buy_value,
            sell_value,
            trade.pnl
        )

        portfolio_result = (
            self.portfolio.apply_trade_result(
                costs["net_pnl"]
            )
        )

        update_trade_net_pnl(
            trade.id,
            costs["net_pnl"]
        )

        if trade_id in self.active_trades:
            del self.active_trades[trade_id]

        return {
            "trade": trade,
            "costs": costs,
            "portfolio": portfolio_result
        }
