
#!/usr/bin/env python3
import sys, os
sys.path.insert(0, ".")
try:
    import requests
except ImportError:
    print("❌ requests не установлен")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

try:
    from config import XROCKET_API_URL, XROCKET_TOKEN
except Exception as e:
    print(f"❌ Не удалось импортировать config: {e}")
    sys.exit(1)

print("=== ПРОВЕРКА XRocket ===")
print(f"XROCKET_API_URL = {XROCKET_API_URL}")
print(f"XROCKET_TOKEN = {'***' + XROCKET_TOKEN[-4:] if XROCKET_TOKEN and len(XROCKET_TOKEN) > 4 else ('НЕ УСТАНОВЛЕН')}")
if not XROCKET_API_URL:
    print("❌ XROCKET_API_URL пустой! Проверь .env")
else:
    import socket
    host = str(XROCKET_API_URL).replace("https://", "").replace("http://", "").split("/")[0]
    try:
        ip = socket.gethostbyname(host)
        print(f"✅ DNS {host} -> {ip}")
    except Exception as e:
        print(f"❌ DNS {host}: {e}")
    # Тест POST /invoice
    if XROCKET_TOKEN:
        try:
            payload = {"amount": 0.01, "currency": "USDT", "description": "test"}
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {XROCKET_TOKEN}"}
            r = requests.post(f"{str(XROCKET_API_URL).rstrip('/')}/invoice", json=payload, headers=headers, timeout=15)
            print(f"POST /invoice -> {r.status_code} (тело: {r.text[:200]})")
        except Exception as e:
            print(f"POST /invoice -> ОШИБКА: {e}")
    else:
        print("⚠️ XROCKET_TOKEN не задан — пропускаю POST")
print("=== КОНЕЦ ===")
