import os
from datetime import (
    datetime,
    timedelta
)
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed
)

from dotenv import load_dotenv
from kiteconnect import KiteConnect

from src.universe.nifty500 import (
    Nifty500
)

from src.universe.instrument_lookup import (
    InstrumentLookup
)

from src.scanner.momentum_scanner import (
    MomentumScanner
)

load_dotenv()

kite = KiteConnect(
    api_key=os.getenv(
        "KITE_API_KEY"
    )
)

kite.set_access_token(
    os.getenv(
        "KITE_ACCESS_TOKEN"
    )
)

print(
    "Downloading instruments..."
)

instruments = kite.instruments(
    "NSE"
)

token_map = (
    InstrumentLookup.build_map(
        instruments
    )
)

watchlist = (
    Nifty500.load()
)

print(
    "Universe Size:",
    len(
        watchlist
    )
)

scanner = MomentumScanner()

to_date = datetime.now()

from_date = (
    to_date
    -
    timedelta(
        days=90
    )
)

results = []


def scan_symbol(
    symbol
):

    token = token_map.get(
        symbol
    )

    if not token:
        print(
            "No token:",
            symbol
        )
        return None

    try:

        candles = kite.historical_data(
            instrument_token=token,
            from_date=from_date,
            to_date=to_date,
            interval="day"
        )

        if not candles:
            print(
                "No candles:",
                symbol
            )
            return None

        result = (
            scanner.scan(
                symbol=symbol,
                candles=candles
            )
        )

        print(
            "Scanned:",
            symbol
        )

        return result

    except Exception as e:

        print(
            "Error:",
            symbol,
            str(
                e
            )
        )

        return None


with ThreadPoolExecutor(
    max_workers=2
) as executor:

    futures = [
        executor.submit(
            scan_symbol,
            symbol
        )
        for symbol
        in watchlist
    ]

    for future in as_completed(
        futures
    ):

        result = future.result()

        if result:

            results.append(
                result
            )

print(
    "Total scanned:",
    len(
        results
    )
)

results = sorted(
    results,
    key=lambda x:
    x["score"],
    reverse=True
)

print(
    "\nTop Results\n"
)

for r in results[
    :20
]:
    print(
        r
    )
