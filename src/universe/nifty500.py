import csv


class Nifty500:

    @staticmethod
    def load(
        filepath="data/nifty500.csv"
    ):

        symbols = []

        with open(
            filepath,
            newline=""
        ) as file:

            reader = csv.DictReader(
                file
            )

            for row in reader:

                if (
                    row[
                        "Symbol"
                    ]
                ):

                    symbols.append(
                        row[
                            "Symbol"
                        ]
                    )

        return symbols
