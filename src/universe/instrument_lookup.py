class InstrumentLookup:

    @staticmethod
    def build_map(
        instruments
    ):

        mapping = {}

        for i in instruments:

            if (
                i["exchange"]
                ==
                "NSE"
            ):

                mapping[
                    i["tradingsymbol"]
                ] = i[
                    "instrument_token"
                ]

        return mapping
