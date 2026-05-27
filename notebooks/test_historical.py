import os
from dotenv import load_dotenv
from kiteconnect import KiteConnect

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

candles = kite.historical_data(
    instrument_token=408065,
    from_date="2025-01-01",
    to_date="2025-03-01",
    interval="day"
)

scanner = MomentumScanner()

result = scanner.scan(
    symbol="INFY",
    candles=candles
)

print(
    result
)
