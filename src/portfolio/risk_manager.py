class RiskManager:

    ATR_MULTIPLIER = 1.5

    def __init__(
        self,
        entry_price,
        atr
    ):
        self.entry_price = entry_price
        self.highest_price = entry_price
        self.atr = atr

        self.trailing_stop = (
            entry_price
            -
            (atr * self.ATR_MULTIPLIER)
        )

    def update(
        self,
        current_price,
        current_atr
    ):
        self.atr = current_atr

        if current_price > self.highest_price:

            self.highest_price = current_price

            new_stop = (
                current_price
                -
                (current_atr * self.ATR_MULTIPLIER)
            )

            if new_stop > self.trailing_stop:
                self.trailing_stop = new_stop

        stop_hit = (
            current_price <= self.trailing_stop
        )

        profit_pct = (
            (current_price - self.entry_price)
            /
            self.entry_price
            *
            100
        )

        profit_rs = (
            (current_price - self.entry_price)
        )

        return {
            "current_price": current_price,
            "highest_price": self.highest_price,
            "trailing_stop": round(self.trailing_stop, 2),
            "stop_hit": stop_hit,
            "profit_pct": round(profit_pct, 2),
            "profit_rs": round(profit_rs, 2)
        }
