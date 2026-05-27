import os
import json
from src.config.settings import (
    STARTING_CAPITAL,
    BASE_CAPITAL,
    KILL_SWITCH,
    PROFIT_BOOK_PERCENT,
    COMPOUND_PERCENT,
    MIN_PROFIT_BOOK_AMOUNT,
    MIN_PROFIT_BOOK_PERCENT
)

STATE_FILE = "data/portfolio_state.json"


class PortfolioManager:

    def __init__(self):
        state = self._load_state()
        self.current_capital = state["current_capital"]
        self.base_capital = state["base_capital"]
        self.booked_profit = state["booked_profit"]

    def _load_state(self):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            return {
                "current_capital": STARTING_CAPITAL,
                "base_capital": BASE_CAPITAL,
                "booked_profit": 0
            }

    def _save_state(self):
        os.makedirs("data", exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump({
                "current_capital": self.current_capital,
                "base_capital": self.base_capital,
                "booked_profit": self.booked_profit
            }, f)

    def apply_trade_result(self, pnl):

        self.current_capital += pnl

        if pnl > 0:

            profit_percent = (
                pnl / self.base_capital
            )

            eligible_for_booking = (
                pnl >= MIN_PROFIT_BOOK_AMOUNT
                and
                profit_percent >=
                MIN_PROFIT_BOOK_PERCENT
            )

            if self.current_capital < self.base_capital:
                self._save_state()
                return {
                    "capital": self.current_capital,
                    "base_capital": self.base_capital,
                    "booked_profit": self.booked_profit,
                    "mode": "recovery"
                }

            if eligible_for_booking:

                profit_to_book = (
                    pnl * PROFIT_BOOK_PERCENT
                )

                profit_to_compound = (
                    pnl * COMPOUND_PERCENT
                )

                self.booked_profit += profit_to_book
                self.current_capital -= profit_to_book
                self.base_capital += profit_to_compound

                mode = "normal"

            else:
                mode = "small_profit"

            self._save_state()

            return {
                "capital": self.current_capital,
                "base_capital": self.base_capital,
                "booked_profit": self.booked_profit,
                "mode": mode
            }

        self._save_state()

        return {
            "capital": self.current_capital,
            "base_capital": self.base_capital,
            "booked_profit": self.booked_profit,
            "mode": "loss"
        }

    def portfolio_paused(self):
        return (
            self.current_capital <= KILL_SWITCH
        )
