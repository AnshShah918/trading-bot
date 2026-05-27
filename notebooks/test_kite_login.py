import os

from dotenv import load_dotenv
from kiteconnect import KiteConnect

load_dotenv()

kite = KiteConnect(
    api_key=os.getenv(
        "KITE_API_KEY"
    )
)

print(
    "\nLogin URL:\n"
)

print(
    kite.login_url()
)

request_token = input(
    "\nPaste request token: "
)

data = kite.generate_session(
    request_token=request_token,
    api_secret=os.getenv(
        "KITE_API_SECRET"
    )
)

access_token = data[
    "access_token"
]

print(
    "\nNew Access Token:\n"
)

print(
    access_token
)

with open(
    ".env",
    "w"
) as f:

    f.write(
        f"KITE_API_KEY={os.getenv('KITE_API_KEY')}\n"
    )

    f.write(
        f"KITE_API_SECRET={os.getenv('KITE_API_SECRET')}\n"
    )

    f.write(
        f"KITE_ACCESS_TOKEN={access_token}\n"
    )

print(
    "\n.env updated"
)
