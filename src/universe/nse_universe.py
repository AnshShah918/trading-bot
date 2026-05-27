class NSEUniverse:

    @staticmethod
    def build(
        instruments,
        limit=500
    ):

        equities = []

        for i in instruments:

            symbol = i[
                "tradingsymbol"
            ]

            if (
                i["exchange"]
                == "NSE"
                and
                i["segment"]
                == "NSE"
                and
                i["instrument_type"]
                == "EQ"
                and
                "-" not in symbol
            ):

                equities.append(
                    i
                )

        equities = sorted(
            equities,
            key=lambda x:
            x.get(
                "instrument_token",
                0
            )
        )

        return [
            e[
                "tradingsymbol"
            ]
            for e
            in equities[
                :limit
            ]
        ]
