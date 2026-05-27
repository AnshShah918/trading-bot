from src.config.settings import TRAILING_STOP_PERCENT


class RiskManager:

    def __init__(self, entry_value):

        self.entry_value = entry_value
        self.highest_value = entry_value

        self.trailing_stop = entry_value * (
            1 - TRAILING_STOP_PERCENT
        )

    def update(self, current_value, close_confirmed=False):

        if current_value > self.highest_value:

            self.highest_value = current_value

            new_stop = self.highest_value * (
                1 - TRAILING_STOP_PERCENT
            )

            if new_stop > self.trailing_stop:
                self.trailing_stop = new_stop

        stop_hit = (
            close_confirmed and
            current_value <= self.trailing_stop
        )

        return {
            "current_value": current_value,
            "highest_value": self.highest_value,
            "trailing_stop": self.trailing_stop,
            "stop_hit": stop_hit
        }
