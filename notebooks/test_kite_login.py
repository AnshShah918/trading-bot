import os
from dotenv import load_dotenv, set_key
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

set_key(
    ".env",
    "KITE_ACCESS_TOKEN",
    access_token
)

print(
    "\n.env updated safely"
)
