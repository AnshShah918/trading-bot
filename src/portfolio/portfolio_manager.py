from src.config.settings import (
    STARTING_CAPITAL,
    BASE_CAPITAL,
    KILL_SWITCH,
    PROFIT_BOOK_PERCENT,
    COMPOUND_PERCENT,
    MIN_PROFIT_BOOK_AMOUNT,
    MIN_PROFIT_BOOK_PERCENT
)

from src.memory.trade_repository import (
    get_open_trades
)


class PortfolioManager:

    def __init__(self):

        self.current_capital = (
            STARTING_CAPITAL
        )

        self.base_capital = (
            BASE_CAPITAL
        )

        self.booked_profit = 0

        self.reserved_capital = 0

        self.rebuild_state()

    def rebuild_state(self):

        open_trades = (
            get_open_trades()
        )

        deployed_capital = sum(
            t.entry_price
            *
            t.quantity
            for t in open_trades
        )

        self.reserved_capital = (
            deployed_capital
        )

    def available_capital(self):

        return (
            self.current_capital
            -
            self.reserved_capital
        )

    def reserve_capital(
        self,
        amount
    ):

        if (
            amount
            >
            self.available_capital()
        ):
            return False

        self.reserved_capital += amount

        return True

    def release_capital(
        self,
        amount
    ):

        self.reserved_capital = max(
            0,
            self.reserved_capital
            -
            amount
        )

    def apply_trade_result(
        self,
        pnl
    ):

        self.current_capital += pnl

        if pnl > 0:

            profit_percent = (
                pnl
                /
                self.base_capital
            )

            eligible_for_booking = (
                pnl
                >=
                MIN_PROFIT_BOOK_AMOUNT
                and
                profit_percent
                >=
                MIN_PROFIT_BOOK_PERCENT
            )

            # Recovery Mode
            if (
                self.current_capital
                <
                self.base_capital
            ):

                return {
                    "capital": self.current_capital,
                    "base_capital": self.base_capital,
                    "booked_profit": self.booked_profit,
                    "reserved_capital": self.reserved_capital,
                    "available_capital": (
                        self.available_capital()
                    ),
                    "mode": "recovery"
                }

            # Meaningful Profit Booking
            if eligible_for_booking:

                profit_to_book = (
                    pnl
                    *
                    PROFIT_BOOK_PERCENT
                )

                profit_to_compound = (
                    pnl
                    *
                    COMPOUND_PERCENT
                )

                self.booked_profit += (
                    profit_to_book
                )

                self.current_capital -= (
                    profit_to_book
                )

                self.base_capital += (
                    profit_to_compound
                )

                mode = "normal"

            else:

                mode = "small_profit"

            return {
                "capital": self.current_capital,
                "base_capital": self.base_capital,
                "booked_profit": self.booked_profit,
                "reserved_capital": self.reserved_capital,
                "available_capital": (
                    self.available_capital()
                ),
                "mode": mode
            }

        return {
            "capital": self.current_capital,
            "base_capital": self.base_capital,
            "booked_profit": self.booked_profit,
            "reserved_capital": self.reserved_capital,
            "available_capital": (
                self.available_capital()
            ),
            "mode": "loss"
        }

    def portfolio_paused(self):

        return (
            self.current_capital
            <=
            KILL_SWITCH
        )