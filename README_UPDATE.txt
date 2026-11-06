=== ГОТОВО ===

Что исправлено:
- Создан xrocket_pay.py (модуль для XRocket)
- Создан handlers/payment.py (исправленная оплата, без pay.ton-rocket.com)
- Исправлен .env (убран мёртвый домен)
- Исправлен requirements.txt (aiohttp==3.10.10)

Что делать дальше (на сервере через панель или Termius):
1. Убедись, что в .env прописан твой реальный XROCKET_API_URL из панели XRocket и XROCKET_TOKEN.
2. Установи пакеты: pip install -r requirements.txt
3. Проверь: python3 verify.py
4. Запусти: nohup python3 bot.py > bot.log 2>&1 &
5. Проверь лог: cat bot.log

Если verify.py показывает POST /invoice -> 200 или 201 — всё работает.
