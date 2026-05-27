from src.config.settings import (
    DEFAULT_POSITION_SIZE,
    GOOD_SETUP_SIZE,
    HIGH_CONVICTION_MAX
)


class PositionManager:

    def __init__(self, capital):
        self.capital = capital

    def calculate_position(
        self,
        setup_type="default",
        override=False,
        override_percent=None
    ):

        if override:

            if (
                override_percent is None or
                override_percent > HIGH_CONVICTION_MAX
            ):
                raise ValueError(
                    "Override exceeds allowed limit"
                )

            allocation = override_percent

        else:

            if setup_type == "good":
                allocation = GOOD_SETUP_SIZE
            else:
                allocation = DEFAULT_POSITION_SIZE

        position_size = self.capital * allocation

        return {
            "allocation_percent": allocation,
            "position_size": position_size
        }
