import os
from dotenv import load_dotenv
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN", "")
XROCKET_TOKEN = os.getenv("XROCKET_TOKEN", "")
XROCKET_API_URL = os.getenv("XROCKET_API_URL", "").strip().rstrip("/") or None
CRYPTO_BOT_TESTNET = os.getenv("CRYPTO_BOT_TESTNET", "false").lower() == "true"
DEFAULT_CURRENCY = os.getenv("DEFAULT_CURRENCY", "USDT")
PROXY_URL = os.getenv("PROXY_URL", "").strip() or None
PAYMENT_PROXY = os.getenv("PAYMENT_PROXY", "").strip() or None
if PAYMENT_PROXY and "://" not in PAYMENT_PROXY:
    PAYMENT_PROXY = None
REFERRAL_PERCENT = float(os.getenv("REFERRAL_PERCENT", "10") or 10)
MIN_WITHDRAW = float(os.getenv("MIN_WITHDRAW", "1.0") or 1)
BOT_USERNAME = os.getenv("BOT_USERNAME", "")
