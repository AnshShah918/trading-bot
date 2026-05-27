from src.memory.trade_repository import (
    open_trade,
    close_trade
)

from src.portfolio.risk_manager import (
    RiskManager
)

from src.portfolio.portfolio_manager import (
    PortfolioManager
)

from src.utils.cost_calculator import (
    calculate_trade_costs
)


class PaperEngine:

    def __init__(self):

        self.active_trades = {}

        self.portfolio = (
            PortfolioManager()
        )

    def open_position(
        self,
        symbol,
        entry_price,
        quantity,
        entry_reason,
        current_stop=None
    ):

        position_value = (
            entry_price
            *
            quantity
        )

        if not (
            self.portfolio
            .reserve_capital(
                position_value
            )
        ):
            raise Exception(
                "Insufficient portfolio capital"
            )

        trade = open_trade(
            symbol=symbol,
            entry_price=entry_price,
            quantity=quantity,
            entry_reason=entry_reason,
            current_stop=current_stop
        )

        self.active_trades[
            trade.id
        ] = RiskManager(
            position_value
        )

        return trade

    def update_position(
        self,
        trade_id,
        current_value,
        close_confirmed=False
    ):

        rm = self.active_trades.get(
            trade_id
        )

        if not rm:
            return None

        return rm.update(
            current_value,
            close_confirmed
        )

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
            trade.entry_price
            *
            trade.quantity
        )

        sell_value = (
            trade.exit_price
            *
            trade.quantity
        )

        self.portfolio.release_capital(
            buy_value
        )

        costs = (
            calculate_trade_costs(
                buy_value,
                sell_value,
                trade.pnl
            )
        )

        portfolio_result = (
            self.portfolio
            .apply_trade_result(
                costs["net_pnl"]
            )
        )

        if (
            trade_id
            in
            self.active_trades
        ):
            del self.active_trades[
                trade_id
            ]

        return {
            "trade": trade,
            "costs": costs,
            "portfolio": portfolio_result
        }