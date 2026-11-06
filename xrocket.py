import logging, aiohttp
logger = logging.getLogger(__name__)
_WORKING = None
def _connector():
    from config import PAYMENT_PROXY
    if PAYMENT_PROXY and "://" in PAYMENT_PROXY:
        try:
            from aiohttp_socks import ProxyConnector
            return ProxyConnector.from_url(PAYMENT_PROXY, rdns=True)
        except Exception as e:
            logger.warning(f"Proxy error: {e}")
    return None
def _bases():
    global _WORKING
    from config import XROCKET_API_URL
    if XROCKET_API_URL:
        return [XROCKET_API_URL]
    if _WORKING:
        return [_WORKING, "https://pay.ton-rocket.com", "https://pay.xrocket.exchange"]
    return ["https://pay.ton-rocket.com", "https://pay.xrocket.exchange"]
async def _request(method, path, json_data=None, params=None):
    global _WORKING
    from config import XROCKET_TOKEN
    if not XROCKET_TOKEN:
        raise Exception("XROCKET_TOKEN не указан в .env")
    headers = {"Rocket-Pay-Key": XROCKET_TOKEN, "Content-Type": "application/json"}
    last_err = None
    for base in _bases():
        url = base + path
        try:
            async with aiohttp.ClientSession(connector=_connector(), timeout=aiohttp.ClientTimeout(total=25)) as s:
                async with (s.post(url, headers=headers, json=json_data) if method == "POST" else s.get(url, headers=headers, params=params)) as r:
                    text = await r.text()
                    logger.info(f"xRocket {method} {url}: {r.status} | {text[:300]}")
                    if r.status not in (200, 201):
                        raise Exception(f"HTTP {r.status}: {text[:200]}")
                    _WORKING = base
                    data = await r.json(content_type=None)
                    if isinstance(data, dict) and data.get("success") is False:
                        raise Exception(str(data.get("error") or data.get("message") or data)[:200])
                    return data.get("data") if isinstance(data, dict) and "data" in data else data
        except Exception as e:
            if str(e).startswith("HTTP"):
                raise
            last_err = e
            continue
    raise Exception(f"xRocket недоступен: {last_err}")
async def create_invoice(amount, description="Покупка", payload="", currency=None):
    from config import DEFAULT_CURRENCY
    body = {"amount": float(amount), "currency": currency or DEFAULT_CURRENCY, "description": str(description)[:1024], "payload": str(payload or ""), "commentsEnabled": False, "expiredIn": 3600}
    result = await _request("POST", "/tg-invoices", body)
    if not isinstance(result, dict):
        raise Exception("xRocket: пустой ответ")
    pay_url = result.get("url") or result.get("link") or result.get("pay_url") or result.get("miniAppPayUrl") or result.get("webPayUrl")
    inv_id = result.get("id") or result.get("invoice_id") or result.get("uuid")
    if not inv_id or not pay_url:
        raise Exception(f"xRocket: нет id/url: {str(result)[:200]}")
    return {"invoice_id": str(inv_id), "pay_url": pay_url, "status": str(result.get("status", "active")).lower()}
async def get_invoice(invoice_id):
    return await _request("GET", f"/tg-invoices/{invoice_id}")
async def check_invoice(invoice_id):
    result = await get_invoice(invoice_id)
    status = str(result.get("status", "")).lower() if isinstance(result, dict) else ""
    return {"status": status or "unknown", "paid": status == "paid"}
