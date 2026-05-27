import os
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from kiteconnect import KiteConnect

from src.universe.nifty500 import Nifty500
from src.universe.instrument_lookup import InstrumentLookup
from src.scanner.momentum_scanner import MomentumScanner

load_dotenv()

kite = KiteConnect(
    api_key=os.getenv("KITE_API_KEY")
)

kite.set_access_token(
    os.getenv("KITE_ACCESS_TOKEN")
)

instruments = kite.instruments("NSE")

token_map = InstrumentLookup.build_map(
    instruments
)

watchlist = Nifty500.load()

scanner = MomentumScanner()

to_date = datetime.now()
from_date = to_date - timedelta(days=365)

results = []
errors = []


def scan_symbol(symbol):

    token = token_map.get(symbol)

    if not token:
        return None

    try:

        candles = kite.historical_data(
            instrument_token=token,
            from_date=from_date,
            to_date=to_date,
            interval="day"
        )

        if not candles:
            return None

        return scanner.scan(
            symbol=symbol,
            candles=candles
        )

    except Exception as e:
        errors.append((symbol, str(e)))
        return None


print("Scanning universe...")

with ThreadPoolExecutor(max_workers=2) as executor:

    futures = {
        executor.submit(scan_symbol, symbol): symbol
        for symbol in watchlist
    }

    done = 0

    for future in as_completed(futures):

        result = future.result()
        done += 1

        if result:
            results.append(result)

        if done % 50 == 0:
            print(
                f"  {done}/{len(watchlist)} scanned..."
            )

results = sorted(
    results,
    key=lambda x: x["score"],
    reverse=True
)

strong = [r for r in results if r["tier"] == "STRONG"]
watch  = [r for r in results if r["tier"] == "WATCH"]

print(f"\nDone. {len(results)} scanned, {len(errors)} errors")
print(f"STRONG: {len(strong)}  |  WATCH: {len(watch)}\n")

print("=" * 60)
print("STRONG SETUPS")
print("=" * 60)

for r in strong:
    print(r)

print("\n")
print("=" * 60)
print(f"TOP 10 WATCH")
print("=" * 60)

for r in watch[:10]:
    print(r)
