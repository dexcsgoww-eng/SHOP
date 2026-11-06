import shutil
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = Path(__file__).resolve().parent
NEED = ["bot.py", "config.py", "database.py", "keyboards.py", "texts.py", "utils.py", "handlers"]

XROCKET_PAY = r'''
import asyncio
import html
import json
import logging
import os
import socket
import time

import aiohttp
import aiosqlite
from aiohttp.abc import AbstractResolver
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import config
import database as db
import keyboards as kb
import texts
from utils import send_or_edit

log = logging.getLogger("xrocket")
router = Router()

API_HOST = "pay.ton-rocket.com"
API_BASE = "https://" + API_HOST
XROCKET_IP = os.getenv("XROCKET_IP", "").strip()
CURRENCY = "USDT"
INVOICE_TTL = 3600
WATCH_TIME = 1800
POLL_EVERY = 8
TOPUP_MIN = 1.0
TOPUP_MAX = 10000.0
FINAL = ("done", "refunded", "expired", "cancelled", "canceled", "error", "missing")

_TASKS = set()
_WATCHING = set()
_LOCKS = {}


class XRState(StatesGroup):
    custom_amount = State()


class XRocketError(Exception):
    pass


class XRResolver(AbstractResolver):
    def __init__(self):
        self._sys = aiohttp.ThreadedResolver()

    async def resolve(self, host, port=0, family=socket.AF_INET):
        if XROCKET_IP and host == API_HOST:
            return [{"hostname": host, "host": XROCKET_IP, "port": port,
                     "family": socket.AF_INET, "proto": 0, "flags": 0}]
        return await self._sys.resolve(host, port, family)

    async def close(self):
        await self._sys.close()


def _proxy_list():
    res = []
    for p in (config.PAYMENT_PROXY, config.PROXY_URL):
        if p and "://" in p and p.strip() not in res:
            res.append(p.strip())
    return res


def _connector_and_proxy():
    for p in _proxy_list():
        scheme = p.split("://", 1)[0].lower()
        if scheme in ("http", "https"):
            return None, p
        if scheme.startswith("socks"):
            try:
                from aiohttp_socks import ProxyConnector
            except ImportError:
                raise XRocketError("для SOCKS-прокси установите пакет: pip install aiohttp-socks")
            return ProxyConnector.from_url(p), None
    return aiohttp.TCPConnector(resolver=XRResolver()), None


async def init_db():
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.execute("""CREATE TABLE IF NOT EXISTS xr_invoices (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, kind TEXT NOT NULL,
            pid INTEGER DEFAULT 0, amount REAL NOT NULL, status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now')))""")
        await c.commit()


async def _save(inv_id, uid, kind, pid, amount):
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.execute("INSERT INTO xr_invoices (id, user_id, kind, pid, amount) VALUES (?, ?, ?, ?, ?)",
                        (inv_id, uid, kind, pid, amount))
        await c.commit()


async def _get(inv_id):
    async with aiosqlite.connect(db.DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        row = await (await c.execute("SELECT * FROM xr_invoices WHERE id=?", (inv_id,))).fetchone()
        return dict(row) if row else None


async def _set(inv_id, status):
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.execute("UPDATE xr_invoices SET status=? WHERE id=?", (status, inv_id))
        await c.commit()


async def _claim(inv_id):
    async with aiosqlite.connect(db.DB_PATH) as c:
        cur = await c.execute("UPDATE xr_invoices SET status='processing' WHERE id=? AND status='active'", (inv_id,))
        await c.commit()
        return cur.rowcount == 1


async def _api(method, path, body=None):
    if not config.XROCKET_TOKEN:
        raise XRocketError("XROCKET_TOKEN не задан в .env")
    connector, proxy = _connector_and_proxy()
    kw = {
        "headers": {"Rocket-Pay-Key": config.XROCKET_TOKEN, "Accept": "application/json"},
        "timeout": aiohttp.ClientTimeout(total=30),
    }
    if proxy:
        kw["proxy"] = proxy
    if body is not None:
        kw["json"] = body
    try:
        async with aiohttp.ClientSession(connector=connector) as s:
            async with s.request(method, API_BASE + path, **kw) as r:
                raw = await r.text()
                try:
                    data = json.loads(raw)
                except ValueError:
                    data = {}
                if not isinstance(data, dict):
                    data = {}
                if r.status >= 400 or data.get("success") is False:
                    msg = data.get("message") or data.get("title") or raw[:200] or "ошибка"
                    raise XRocketError(f"HTTP {r.status}: {msg}")
                payload = data.get("data", data)
                return payload if isinstance(payload, dict) else {}
    except XRocketError:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
        raise XRocketError(f"нет соединения с {API_HOST}: {type(e).__name__}: {e}")


async def create_invoice(amount, description):
    body = {"amount": round(float(amount), 2), "numPayments": 1, "currency": CURRENCY,
            "description": description[:250], "expiredIn": INVOICE_TTL}
    inv = await _api("POST", "/tg-invoices", body)
    if not inv.get("id") or not inv.get("link"):
        raise XRocketError(f"неожиданный ответ API: {inv}")
    return inv


async def get_invoice(inv_id):
    return await _api("GET", f"/tg-invoices/{inv_id}")


async def _safe_send(bot, uid, text):
    try:
        await bot.send_message(uid, text)
    except Exception as e:
        log.warning(f"send to {uid}: {e}")


async def _notify_admins(bot, text):
    for aid in config.ADMIN_IDS:
        try:
            await bot.send_message(aid, text)
        except Exception:
            pass


async def _finalize(bot, inv):
    uid = inv["user_id"]
    amount = float(inv["amount"])

    if inv["kind"] == "topup":
        await db.add_balance(uid, amount)
        await _set(inv["id"], "done")
        user = await db.get_user(uid) or {}
        text = await texts.T("tpl_topup_success", amount=texts.money(amount),
                             balance=texts.money(user.get("balance", 0)))
        await _safe_send(bot, uid, text)
        return "done"

    pid = int(inv["pid"] or 0)
    prod = await db.get_product(pid)
    got = await db.buy_item(pid, uid) if prod else None
    if not got:
        await db.add_balance(uid, amount)
        await _set(inv["id"], "refunded")
        await _safe_send(bot, uid, f"⚠️ Оплата получена, но товар «{texts.pname(prod)}» закончился. "
                                   f"Деньги ({texts.money(amount)}$) зачислены на ваш баланс.")
        await _notify_admins(bot, f"⚠️ xRocket: товар закончился после оплаты. Счёт {inv['id']}, "
                                  f"{texts.money(amount)}$ возвращены пользователю {uid}.")
        return "refunded"

    item_id, content = got
    oid = await db.create_order(uid, pid, amount, "xrocket", inv["id"])
    await db.complete_order(oid, item_id)
    await _set(inv["id"], "done")
    text = await texts.T("tpl_purchase_done", product=texts.pname(prod), content=html.escape(str(content)))
    await _safe_send(bot, uid, text)
    await _notify_admins(bot, f"💰 Покупка через xRocket\nПользователь: {uid}\n"
                              f"📦 {kb._clean(prod.get('name'))}\n💵 {texts.money(amount)}$")
    return "done"


async def check_and_deliver(bot, inv_id):
    inv = await _get(inv_id)
    if not inv:
        return "missing"
    if inv["status"] != "active":
        return inv["status"]

    lock = _LOCKS.setdefault(inv_id, asyncio.Lock())
    async with lock:
        inv = await _get(inv_id)
        if inv["status"] != "active":
            return inv["status"]
        try:
            remote = await get_invoice(inv_id)
        except Exception as e:
            log.warning(f"xrocket check {inv_id}: {e}")
            return "pending"

        status = str(remote.get("status", "")).lower()
        if status in ("expired", "cancelled", "canceled"):
            await _set(inv_id, status)
            return status
        if status != "paid":
            return "pending"
        if not await _claim(inv_id):
            return "pending"
        try:
            return await _finalize(bot, inv)
        except Exception as e:
            log.exception(f"xrocket finalize {inv_id}: {e}")
            await _set(inv_id, "error")
            await _notify_admins(bot, f"⚠️ Ошибка выдачи xRocket-счёта {inv_id}: {e}. Проверьте вручную.")
            return "error"


async def _watch(bot, inv_id):
    if inv_id in _WATCHING:
        return
    _WATCHING.add(inv_id)
    try:
        deadline = time.time() + WATCH_TIME
        while time.time() < deadline:
            await asyncio.sleep(POLL_EVERY)
            if await check_and_deliver(bot, inv_id) in FINAL:
                break
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.exception(f"watch {inv_id}: {e}")
    finally:
        _WATCHING.discard(inv_id)
        _LOCKS.pop(inv_id, None)


def _spawn(bot, inv_id):
    t = asyncio.create_task(_watch(bot, inv_id))
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)


async def resume(bot):
    async with aiosqlite.connect(db.DB_PATH) as c:
        rows = await (await c.execute(
            "SELECT id FROM xr_invoices WHERE status='active' AND created_at >= datetime('now', '-1 hour')")).fetchall()
    for (inv_id,) in rows:
        _spawn(bot, inv_id)
    if rows:
        log.info(f"xRocket: восстановлено отслеживание счетов: {len(rows)}")


async def _answer(call, st):
    msgs = {
        "done": ("✅ Оплата получена!", False),
        "refunded": ("⚠️ Товар закончился, деньги зачислены на баланс", True),
        "pending": ("⏳ Оплата пока не поступила. Попробуйте через минуту", True),
        "processing": ("⏳ Оплата обрабатывается...", True),
        "expired": ("⌛ Счёт истёк. Создайте новый", True),
        "cancelled": ("❌ Счёт отменён", True),
        "canceled": ("❌ Счёт отменён", True),
        "missing": ("❌ Счёт не найден", True),
    }
    text, alert = msgs.get(st, ("⚠️ Ошибка проверки, попробуйте позже", True))
    await call.answer(text, show_alert=alert)


@router.callback_query(F.data.startswith("pay:xrocket:"))
async def cb_pay(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        pid = int(call.data.split(":")[2])
    except (IndexError, ValueError):
        await call.answer("Ошибка данных", show_alert=True)
        return
    prod = await db.get_product(pid)
    if not prod or not prod.get("is_active"):
        await call.answer("Товар недоступен", show_alert=True)
        return
    if await db.get_available_items_count(pid) <= 0:
        await call.answer("Товар закончился", show_alert=True)
        return
    try:
        inv = await create_invoice(prod["price"], f"Покупка: {kb._clean(prod.get('name'))}")
    except Exception as e:
        log.exception(f"create invoice: {e}")
        await send_or_edit(call, f"❌ Не удалось создать счёт xRocket.\n<code>{html.escape(str(e))}</code>",
                           reply_markup=kb.back_only_kb(f"product:{pid}"))
        await call.answer()
        return
    inv_id = str(inv["id"])
    await _save(inv_id, call.from_user.id, "product", pid, float(prod["price"]))
    text = await texts.T("tpl_pay_invoice", product=texts.pname(prod),
                         price=texts.money(prod["price"]), method="🚀 xRocket")
    await send_or_edit(call, text, reply_markup=kb.check_payment_kb("xrocket", inv_id, inv["link"], pid))
    _spawn(call.bot, inv_id)
    await call.answer()


@router.callback_query(F.data.startswith("check:xrocket:"))
async def cb_check(call: CallbackQuery):
    await _answer(call, await check_and_deliver(call.bot, call.data.split(":")[2]))


async def _show_topup(event, bot, uid, amount):
    try:
        inv = await create_invoice(amount, f"Пополнение баланса {texts.money(amount)}$")
    except Exception as e:
        log.exception(f"topup invoice: {e}")
        await send_or_edit(event, f"❌ Не удалось создать счёт xRocket.\n<code>{html.escape(str(e))}</code>",
                           reply_markup=kb.back_only_kb("topup_method:xrocket"))
        return
    inv_id = str(inv["id"])
    await _save(inv_id, uid, "topup", 0, float(amount))
    text = await texts.T("tpl_topup_invoice", method="🚀 xRocket", amount=texts.money(amount))
    await send_or_edit(event, text, reply_markup=kb.topup_check_kb("xrocket", inv_id, inv["link"]))
    _spawn(bot, inv_id)


@router.callback_query(F.data == "topup_method:xrocket")
async def cb_topup_method(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await send_or_edit(call, await texts.T("tpl_topup_amount", method="🚀 xRocket"),
                       reply_markup=kb.topup_amount_kb("xrocket"))
    await call.answer()


@router.callback_query(F.data.startswith("topup_amt:xrocket:"))
async def cb_topup_amt(call: CallbackQuery, state: FSMContext):
    await state.clear()
    val = call.data.split(":")[2]
    if val == "custom":
        await state.set_state(XRState.custom_amount)
        await send_or_edit(call, f"✏️ Введите сумму пополнения в $ (от {TOPUP_MIN:g} до {TOPUP_MAX:g}):",
                           reply_markup=kb.back_only_kb("topup_method:xrocket"))
        await call.answer()
        return
    try:
        amount = float(val)
    except ValueError:
        await call.answer("Ошибка суммы", show_alert=True)
        return
    await call.answer()
    await _show_topup(call, call.bot, call.from_user.id, amount)


@router.message(XRState.custom_amount)
async def on_custom_amount(message: Message, state: FSMContext):
    try:
        amount = float((message.text or "").replace(",", ".").strip())
    except ValueError:
        amount = None
    if amount is None or not (TOPUP_MIN <= amount <= TOPUP_MAX):
        await message.answer(f"❌ Введите число от {TOPUP_MIN:g} до {TOPUP_MAX:g}")
        return
    await state.clear()
    await _show_topup(message, message.bot, message.from_user.id, amount)


@router.callback_query(F.data.startswith("topup_check:xrocket:"))
async def cb_topup_check(call: CallbackQuery):
    await _answer(call, await check_and_deliver(call.bot, call.data.split(":", 2)[2]))
'''

BOT_PY = r'''
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from config import BOT_TOKEN, PROXY_URL
import database as db
import db_ext
import xrocket_pay
from handlers import user, payment, referral, admin, subscription, chat_member, admin_ext

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)


async def main():
    await db.init_db()
    await db_ext.ensure_schema()
    await xrocket_pay.init_db()

    try:
        import aiogram
        from keyboards import _HAS_STYLE_ICON
        logger.info(f"aiogram={aiogram.__version__} | button style/icon: {'OK' if _HAS_STYLE_ICON else 'NOT SUPPORTED'}")
    except Exception:
        pass

    session = None
    if PROXY_URL and "://" in PROXY_URL:
        logger.info(f"Using proxy: {PROXY_URL}")
        try:
            session = AiohttpSession(proxy=PROXY_URL)
        except Exception as e:
            logger.warning(f"Proxy setup failed: {e}")

    bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    try:
        from middlewares.subscription import SubscriptionMiddleware, watcher_loop
        dp.message.middleware(SubscriptionMiddleware())
        dp.callback_query.middleware(SubscriptionMiddleware())
        asyncio.create_task(watcher_loop())
        logger.info("Subscription middleware enabled")
    except Exception as e:
        logger.warning(f"Subs middleware err: {e}")

    # xrocket_pay первым: он перехватывает свои callback-кнопки раньше payment.py
    dp.include_router(xrocket_pay.router)
    dp.include_router(subscription.router)
    dp.include_router(chat_member.router)
    dp.include_router(admin_ext.router)
    dp.include_router(user.router)
    dp.include_router(payment.router)
    dp.include_router(referral.router)
    dp.include_router(admin.router)

    me = await bot.get_me()
    logger.info(f"Bot @{me.username} started")
    await bot.delete_webhook(drop_pending_updates=True)
    await xrocket_pay.resume(bot)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "chat_member", "my_chat_member"])


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped")
'''

CHECK_PY = r'''
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
'''


def backup(name):
    p = BASE / name
    if p.exists():
        b = p.with_name(p.stem + "_backup_v4" + p.suffix)
        shutil.copy(p, b)
        print("OK backup:", b.name)


def write(name, content):
    (BASE / name).write_text(content.strip() + "\n", encoding="utf-8")
    print("OK write:", name)


def fix_env():
    env = BASE / ".env"
    if not env.exists():
        print("ВНИМАНИЕ: .env не найден. Создайте его: BOT_TOKEN, ADMIN_IDS, XROCKET_TOKEN")
        return
    backup(".env")
    lines = env.read_text(encoding="utf-8").splitlines()
    out, keys = [], set()
    for ln in lines:
        s = ln.strip()
        if s.startswith("XROCKET_API_URL"):
            out.append("# " + ln)
            continue
        if "=" in s and not s.startswith("#"):
            keys.add(s.split("=", 1)[0].strip())
        out.append(ln)
    if "XROCKET_IP" not in keys:
        out.append("# XROCKET_IP=   (IP pay.ton-rocket.com, нужен только если DNS не работает)")
    env.write_text("\n".join(out) + "\n", encoding="utf-8")
    filled = [l for l in lines if l.strip().startswith("XROCKET_TOKEN=") and l.split("=", 1)[1].strip()]
    print("OK .env: XROCKET_TOKEN заполнен" if filled else "ВНИМАНИЕ: заполните XROCKET_TOKEN=... в .env")


def main():
    print("=== UPDATE v4: xRocket ===")
    miss = [n for n in NEED if not (BASE / n).exists()]
    if miss:
        print("ОШИБКА: не найдены:", ", ".join(miss))
        print("Положите этот файл в папку с bot.py и запустите снова.")
        return

    backup("bot.py")
    backup("xrocket_pay.py")
    write("xrocket_pay.py", XROCKET_PAY)
    write("bot.py", BOT_PY)
    write("check_xrocket.py", CHECK_PY)
    fix_env()

    print("=== COMPILE ===")
    files = ["bot.py", "xrocket_pay.py", "check_xrocket.py"]
    r = subprocess.run([sys.executable, "-m", "compileall", "-q", *files], cwd=str(BASE),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        print("ОШИБКА компиляции. Пришлите этот вывод.")
        return
    print("OK compile")

    print("=== IMPORT TEST ===")
    r = subprocess.run([sys.executable, "-c", "import xrocket_pay, bot; print('IMPORT OK')"],
                       cwd=str(BASE), capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout, r.stderr[-1500:] if r.stderr else "")
    if r.returncode != 0:
        print("ОШИБКА импорта. Пришлите этот вывод.")
        return
    print("ГОТОВО. Дальше: python check_xrocket.py, затем python bot.py")


if __name__ == "__main__":
    main()