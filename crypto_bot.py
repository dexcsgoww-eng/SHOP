import logging, aiohttp
logger = logging.getLogger(__name__)
def _connector():
    from config import PAYMENT_PROXY
    if PAYMENT_PROXY and "://" in PAYMENT_PROXY:
        try:
            from aiohttp_socks import ProxyConnector
            return ProxyConnector.from_url(PAYMENT_PROXY, rdns=True)
        except Exception as e:
            logger.warning(f"Proxy error: {e}")
    return None
def _url():
    from config import CRYPTO_BOT_TESTNET
    return "https://testnet-pay.crypt.bot/api" if CRYPTO_BOT_TESTNET else "https://pay.crypt.bot/api"
async def _request(method, params=None):
    from config import CRYPTO_BOT_TOKEN
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    async with aiohttp.ClientSession(connector=_connector(), timeout=aiohttp.ClientTimeout(total=20)) as s:
        async with s.get(f"{_url()}/{method}", headers=headers, params=params) as r:
            text = await r.text()
            logger.info(f"CryptoBot {method}: {r.status} | {text[:300]}")
            if r.status != 200:
                raise Exception(f"HTTP {r.status}: {text[:200]}")
            data = await r.json(content_type=None)
            if data.get("ok"):
                return data.get("result")
            e = data.get("error", {})
            raise Exception(f"{e.get('name','Error')}: {e.get('message','')}")
async def create_invoice(amount, description="Покупка", payload="", currency=None):
    from config import DEFAULT_CURRENCY
    params = {"asset": currency or DEFAULT_CURRENCY, "amount": str(amount), "description": description}
    if payload:
        params["payload"] = payload
    result = await _request("createInvoice", params)
    return {"invoice_id": str(result["invoice_id"]), "pay_url": result.get("pay_url") or result.get("mini_app_invoice_url") or result.get("bot_invoice_url"), "status": result.get("status", "active")}
async def check_invoice(invoice_id):
    result = await _request("getInvoices", {"invoice_ids": invoice_id})
    if result and result.get("items"):
        inv = result["items"][0]
        return {"status": inv["status"], "paid": inv["status"] == "paid"}
    return {"status": "not_found", "paid": False}
