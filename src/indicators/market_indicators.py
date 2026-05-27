class MarketIndicators:

    @staticmethod
    def recent_high(
        candles,
        period=20
    ):

        recent = candles[
            -period:
        ]

        return max(
            c["high"]
            for c
            in recent
        )

    @staticmethod
    def average_volume(
        candles,
        period=20
    ):

        recent = candles[
            -period:
        ]

        return (
            sum(
                c["volume"]
                for c
                in recent
            )
            /
            len(
                recent
            )
        )

    @staticmethod
    def momentum(
        candles,
        period=63
    ):

        relevant = candles[
            -period:
        ]

        first_close = (
            relevant[0]
            ["close"]
        )

        last_close = (
            relevant[-1]
            ["close"]
        )

        return (
            last_close
            -
            first_close
        ) / first_close

    @staticmethod
    def moving_average(
        candles,
        period
    ):

        closes = [
            c["close"]
            for c
            in candles[
                -period:
            ]
        ]

        return (
            sum(closes)
            /
            len(closes)
        )

    @staticmethod
    def fifty_two_week_high(
        candles
    ):

        return max(
            c["high"]
            for c
            in candles
        )

    @staticmethod
    def rsi(
        candles,
        period=14
    ):

        closes = [
            c["close"]
            for c
            in candles
        ]

        gains = []
        losses = []

        for i in range(
            1,
            len(closes)
        ):

            change = (
                closes[i]
                -
                closes[i - 1]
            )

            if change > 0:

                gains.append(
                    change
                )

                losses.append(
                    0
                )

            else:

                gains.append(
                    0
                )

                losses.append(
                    abs(
                        change
                    )
                )

        avg_gain = (
            sum(
                gains[
                    -period:
                ]
            )
            /
            period
        )

        avg_loss = (
            sum(
                losses[
                    -period:
                ]
            )
            /
            period
        )

        if avg_loss == 0:
            return 100

        rs = (
            avg_gain
            /
            avg_loss
        )

        return (
            100
            -
            (
                100
                /
                (
                    1
                    +
                    rs
                )
            )
        )
    @staticmethod
    def atr(
        candles,
        period=14
    ):

        true_ranges = []

        for i in range(
            1,
            len(candles)
        ):

            high = (
                candles[i]["high"]
            )

            low = (
                candles[i]["low"]
            )

            prev_close = (
                candles[
                    i - 1
                ]["close"]
            )

            tr = max(
                high - low,
                abs(
                    high
                    -
                    prev_close
                ),
                abs(
                    low
                    -
                    prev_close
                )
            )

            true_ranges.append(
                tr
            )

        recent = (
            true_ranges[
                -period:
            ]
        )

        return (
            sum(
                recent
            )
            /
            len(
                recent
            )
        )
