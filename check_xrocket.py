import asyncio
import socket

import config
import xrocket_pay as xr


def ok(m):
    print("[OK]   " + m)


def bad(m):
    print("[FAIL] " + m)


async def main():
    print("=== Проверка xRocket ===")
    proxies = xr._proxy_list()
    print("Прокси:", proxies[0] if proxies else "не задан")
    print("XROCKET_IP:", xr.XROCKET_IP or "не задан")
    try:
        ok(f"DNS: {xr.API_HOST} -> {socket.gethostbyname(xr.API_HOST)}")
    except OSError as e:
        bad(f"DNS не резолвит {xr.API_HOST}: {e}")
    if not config.XROCKET_TOKEN:
        bad("XROCKET_TOKEN пуст в .env")
        return
    try:
        await xr._api("GET", "/tg-invoices/0")
        ok("API ответил без ошибки")
    except xr.XRocketError as e:
        msg = str(e)
        if msg.startswith(("HTTP 401", "HTTP 403")):
            bad("токен неверный: " + msg)
        elif msg.startswith("HTTP"):
            ok("сеть работает, API отвечает: " + msg)
        else:
            bad(msg)


if __name__ == "__main__":
    asyncio.run(main())
