import asyncio, logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from database import init_db
from handlers import (user, payment, referral, admin, admin_ext,
                      promocodes, section_buttons, topup,
                      subscription, chat_member)
import xrocket_pay

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

async def main():
    await init_db()
    bot = Bot(BOT_TOKEN, parse_mode="HTML")
    dp = Dispatcher()
    # порядок важен: юзерские ДО админских
    dp.include_router(xrocket_pay.router)
    dp.include_router(subscription.router)
    dp.include_router(chat_member.router)
    dp.include_router(promocodes.router)
    dp.include_router(topup.router)
    dp.include_router(payment.router)
    dp.include_router(referral.router)
    dp.include_router(user.router)
    dp.include_router(section_buttons.router)
    dp.include_router(admin_ext.router)
    dp.include_router(admin.router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
'''

# ═══ config.py ═══
F["config.py"] = '''\
BOT_TOKEN = "9205720021:AAEwsd5SGOVSypJmXkqZ9SqPz79aLpP3Kx8"
ADMIN_IDS = [5482617223]
DB_PATH = "shop.db"
XROCKET_API_KEY = ""
XROCKET_SHOP_ID = ""
REFERRAL_PERCENT = 5
CHANNEL_ID = ""
SUPPORT_URL = "https://t.me/your_support"
'''

# ═══ database.py ═══
F["database.py"] = '''\
import aiosqlite, json, time
from config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE, username TEXT,
            balance REAL DEFAULT 0, referrer_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS categories(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, emoji TEXT DEFAULT '📁',
            description TEXT, image TEXT,
            sort_order INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER, name TEXT, description TEXT,
            price REAL, emoji TEXT DEFAULT '📦', image TEXT,
            sort_order INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1,
            FOREIGN KEY(category_id) REFERENCES categories(id));
        CREATE TABLE IF NOT EXISTS items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER, value TEXT,
            is_sold INTEGER DEFAULT 0, sold_to INTEGER,
            sold_at TIMESTAMP,
            FOREIGN KEY(product_id) REFERENCES products(id));
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, product_id INTEGER, item_id INTEGER,
            price REAL, payment_method TEXT, payment_id TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS withdrawals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, amount REAL, wallet TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS promocodes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE, type TEXT DEFAULT 'discount',
            amount REAL DEFAULT 0, discount_percent REAL DEFAULT 0,
            max_uses INTEGER DEFAULT 0, uses_count INTEGER DEFAULT 0,
            min_purchase REAL DEFAULT 0, product_id INTEGER,
            category_id INTEGER, expires_at TIMESTAMP,
            is_active INTEGER DEFAULT 1, created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS promocode_uses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promocode_id INTEGER, user_id INTEGER,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(promocode_id, user_id));
        CREATE TABLE IF NOT EXISTS section_buttons(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section TEXT, text TEXT, url TEXT,
            callback_data TEXT, is_active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS manual_topups(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, amount REAL, tx_hash TEXT,
            photo_id TEXT, product_id INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS xrocket_payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, invoice_id TEXT, amount REAL,
            status TEXT DEFAULT 'pending', order_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        """)
        await db.commit()

async def _q(sql, params=(), one=False):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, params)
        r = await cur.fetchone() if one else await cur.fetchall()
        return dict(r) if r and one else ([dict(x) for x in r] if r else ([] if not one else None))

async def _e(sql, params=()):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(sql, params)
        await db.commit()
        return cur.lastrowid

# ── users ──
async def get_user(uid):
    return await _q("SELECT * FROM users WHERE user_id=?", (uid,), True)
async def create_user(uid, uname, ref=None):
    await _e("INSERT OR IGNORE INTO users(user_id,username,referrer_id) VALUES(?,?,?)",
             (uid, uname, ref))
    return await get_user(uid)
async def get_or_create_user(uid, uname, ref=None):
    u = await get_user(uid)
    if not u: u = await create_user(uid, uname, ref)
    return u
async def add_balance(uid, amt):
    await _e("UPDATE users SET balance=balance+? WHERE user_id=?", (amt, uid))
async def get_all_users():
    return await _q("SELECT * FROM users ORDER BY id DESC")
async def get_user_count():
    r = await _q("SELECT COUNT(*) as c FROM users", one=True)
    return r["c"] if r else 0

# ── categories ──
async def get_categories():
    return await _q("SELECT * FROM categories WHERE is_active=1 ORDER BY sort_order")
async def get_all_categories():
    return await _q("SELECT * FROM categories ORDER BY sort_order")
async def get_category(cid):
    return await _q("SELECT * FROM categories WHERE id=?", (cid,), True)
async def create_category(name, emoji="📁"):
    return await _e("INSERT INTO categories(name,emoji) VALUES(?,?)", (name, emoji))
async def update_category(cid, **kw):
    for k, v in kw.items():
        await _e(f"UPDATE categories SET {k}=? WHERE id=?", (v, cid))
async def delete_category(cid):
    await _e("DELETE FROM categories WHERE id=?", (cid,))

# ── products ──
async def get_products(cat_id=None):
    if cat_id:
        return await _q("SELECT * FROM products WHERE category_id=? AND is_active=1 ORDER BY sort_order", (cat_id,))
    return await _q("SELECT * FROM products WHERE is_active=1 ORDER BY sort_order")
async def get_all_products():
    return await _q("SELECT * FROM products ORDER BY sort_order")
async def get_product(pid):
    return await _q("SELECT * FROM products WHERE id=?", (pid,), True)
async def create_product(cat_id, name, price, desc=""):
    return await _e("INSERT INTO products(category_id,name,price,description) VALUES(?,?,?,?)",
                    (cat_id, name, price, desc))
async def update_product(pid, **kw):
    for k, v in kw.items():
        await _e(f"UPDATE products SET {k}=? WHERE id=?", (v, pid))
async def delete_product(pid):
    await _e("DELETE FROM products WHERE id=?", (pid,))

# ── items ──
async def get_available_items(pid):
    return await _q("SELECT * FROM items WHERE product_id=? AND is_sold=0", (pid,))
async def get_available_items_count(pid):
    r = await _q("SELECT COUNT(*) as c FROM items WHERE product_id=? AND is_sold=0", (pid,), True)
    return r["c"] if r else 0
async def add_item(pid, value):
    return await _e("INSERT INTO items(product_id,value) VALUES(?,?)", (pid, value))
async def mark_item_sold(iid, uid):
    await _e("UPDATE items SET is_sold=1, sold_to=?, sold_at=CURRENT_TIMESTAMP WHERE id=?", (uid, iid))

# ── orders ──
async def create_order(uid, pid, iid, price, method, pay_id):
    return await _e("INSERT INTO orders(user_id,product_id,item_id,price,payment_method,payment_id) VALUES(?,?,?,?,?,?)",
                    (uid, pid, iid, price, method, pay_id))
async def get_order(oid):
    return await _q("SELECT * FROM orders WHERE id=?", (oid,), True)
async def get_order_by_payment(pay_id):
    return await _q("SELECT * FROM orders WHERE payment_id=?", (pay_id,), True)
async def get_order_by_payment_prefix(prefix):
    return await _q("SELECT * FROM orders WHERE payment_id LIKE ?", (f"{prefix}%",), True)
async def get_user_orders(uid):
    return await _q("SELECT * FROM orders WHERE user_id=? AND status='completed' ORDER BY id DESC", (uid,))
async def update_order_status(oid, status):
    await _e("UPDATE orders SET status=? WHERE id=?", (status, oid))

# ── settings ──
async def get_setting(key, default=None):
    r = await _q("SELECT value FROM settings WHERE key=?", (key,), True)
    return r["value"] if r else default
async def set_setting(key, value):
    await _e("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
             (key, str(value)))

# ── withdrawals ──
async def create_withdrawal(uid, amount, wallet):
    return await _e("INSERT INTO withdrawals(user_id,amount,wallet) VALUES(?,?,?)", (uid, amount, wallet))
async def get_pending_withdrawals():
    return await _q("SELECT * FROM withdrawals WHERE status='pending' ORDER BY id")
async def update_withdrawal(wid, status):
    await _e("UPDATE withdrawals SET status=? WHERE id=?", (status, wid))

# ── manual topups ──
async def create_manual_topup(uid, amount, tx_hash, photo_id, product_id=0):
    return await _e("INSERT INTO manual_topups(user_id,amount,tx_hash,photo_id,product_id) VALUES(?,?,?,?,?)",
                    (uid, amount, tx_hash, photo_id, product_id))
async def get_manual_topup(tid):
    return await _q("SELECT * FROM manual_topups WHERE id=?", (tid,), True)
async def get_pending_manual_topups():
    return await _q("SELECT * FROM manual_topups WHERE status='pending' ORDER BY id")
async def update_manual_topup(tid, status):
    await _e("UPDATE manual_topups SET status=? WHERE id=?", (status, tid))

# ── xrocket ──
async def create_xrocket_payment(uid, inv_id, amount, order_id=None):
    return await _e("INSERT INTO xrocket_payments(user_id,invoice_id,amount,order_id) VALUES(?,?,?,?)",
                    (uid, inv_id, amount, order_id))
async def get_xrocket_payment(inv_id):
    return await _q("SELECT * FROM xrocket_payments WHERE invoice_id=?", (inv_id,), True)
async def update_xrocket_payment(inv_id, status):
    await _e("UPDATE xrocket_payments SET status=? WHERE invoice_id=?", (status, inv_id))

# ── promocodes ──
async def create_promocode(code, ptype="discount", amount=0, discount=0,
                           max_uses=0, min_purchase=0, product_id=None,
                           category_id=None, expires_at=None, created_by=None):
    return await _e(
        "INSERT INTO promocodes(code,type,amount,discount_percent,max_uses,min_purchase,product_id,category_id,expires_at,created_by) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (code, ptype, amount, discount, max_uses, min_purchase, product_id, category_id, expires_at, created_by))

async def get_promocode(code=None, promo_id=None):
    if promo_id:
        return await _q("SELECT * FROM promocodes WHERE id=?", (promo_id,), True)
    return await _q("SELECT * FROM promocodes WHERE UPPER(code)=UPPER(?)", (code,), True)

async def get_promocodes():
    return await _q("SELECT * FROM promocodes ORDER BY id DESC")

async def update_promocode(pid, **kw):
    for k, v in kw.items():
        await _e(f"UPDATE promocodes SET {k}=? WHERE id=?", (v, pid))

async def delete_promocode(pid):
    await _e("DELETE FROM promocode_uses WHERE promocode_id=?", (pid,))
    await _e("DELETE FROM promocodes WHERE id=?", (pid,))

async def toggle_promocode(pid):
    p = await get_promocode(promo_id=pid)
    if p:
        await _e("UPDATE promocodes SET is_active=? WHERE id=?", (0 if p["is_active"] else 1, pid))

async def apply_promocode(code, uid):
    p = await get_promocode(code=code)
    if not p: return {"ok": False, "error": "Промокод не найден"}
    if not p["is_active"]: return {"ok": False, "error": "Промокод неактивен"}
    if p["expires_at"] and p["expires_at"] < datetime.now().strftime("%Y-%m-%d %H:%M:%S"):
        return {"ok": False, "error": "Промокод истёк"}
    if p["max_uses"] > 0 and p["uses_count"] >= p["max_uses"]:
        return {"ok": False, "error": "Лимит использований исчерпан"}
    used = await _q("SELECT id FROM promocode_uses WHERE promocode_id=? AND user_id=?",
                    (p["id"], uid), True)
    if used: return {"ok": False, "error": "Вы уже использовали этот промокод"}
    if p["type"] == "balance":
        await _e("INSERT INTO promocode_uses(promocode_id,user_id) VALUES(?,?)", (p["id"], uid))
        await _e("UPDATE promocodes SET uses_count=uses_count+1 WHERE id=?", (p["id"],))
        await add_balance(uid, p["amount"])
        return {"ok": True, "type": "balance", "amount": p["amount"]}
    else:
        await set_active_promo(uid, p["id"], p["discount_percent"])
        return {"ok": True, "type": "discount", "discount": p["discount_percent"], "code": p["code"]}

async def use_promocode(promo_id, uid):
    try:
        await _e("INSERT OR IGNORE INTO promocode_uses(promocode_id,user_id) VALUES(?,?)", (promo_id, uid))
        await _e("UPDATE promocodes SET uses_count=uses_count+1 WHERE id=?", (promo_id,))
    except: pass

async def set_active_promo(uid, promo_id, pct):
    await set_setting(f"active_promo_{uid}", f"{promo_id}:{pct}")

async def get_active_promo(uid):
    v = await get_setting(f"active_promo_{uid}")
    if not v: return None
    parts = v.split(":")
    if len(parts) == 2: return (int(parts[0]), float(parts[1]))
    return None

async def clear_active_promo(uid):
    await _e("DELETE FROM settings WHERE key=?", (f"active_promo_{uid}",))

async def calculate_price_with_promo(uid, pid, base_price):
    info = {"final_price": base_price, "discount": 0, "promo_code": None, "promo_id": None}
    ap = await get_active_promo(uid)
    if not ap: return info
    promo_id, pct = ap
    p = await get_promocode(promo_id=promo_id)
    if not p or not p["is_active"]: return info
    if p["product_id"] and p["product_id"] != pid: return info
    if p["category_id"]:
        prod = await get_product(pid)
        if prod and prod["category_id"] != p["category_id"]: return info
    if p["min_purchase"] > 0 and base_price < p["min_purchase"]: return info
    disc = round(base_price * pct / 100, 2)
    info["final_price"] = round(base_price - disc, 2)
    info["discount"] = disc
    info["promo_code"] = p["code"]
    info["promo_id"] = promo_id
    return info

# ── section buttons ──
async def sb_list(section=None):
    if section:
        return await _q("SELECT * FROM section_buttons WHERE section=? AND is_active=1 ORDER BY sort_order", (section,))
    return await _q("SELECT * FROM section_buttons ORDER BY section, sort_order")

async def sb_add(section, text, url=None, cb_data=None):
    return await _e("INSERT INTO section_buttons(section,text,url,callback_data) VALUES(?,?,?,?)",
                    (section, text, url, cb_data))

async def sb_get(sid):
    return await _q("SELECT * FROM section_buttons WHERE id=?", (sid,), True)

async def sb_delete(sid):
    await _e("DELETE FROM section_buttons WHERE id=?", (sid,))

async def sb_toggle(sid):
    b = await sb_get(sid)
    if b: await _e("UPDATE section_buttons SET is_active=? WHERE id=?", (0 if b["is_active"] else 1, sid))

async def sb_update(sid, **kw):
    for k, v in kw.items():
        await _e(f"UPDATE section_buttons SET {k}=? WHERE id=?", (v, sid))

# ── referrals ──
async def set_referrer(uid, ref_id):
    u = await get_user(uid)
    if u and not u["referrer_id"] and uid != ref_id:
        await _e("UPDATE users SET referrer_id=? WHERE user_id=?", (ref_id, uid))
async def get_referrer(uid):
    u = await get_user(uid)
    return u["referrer_id"] if u else None
async def get_referral_count(uid):
    r = await _q("SELECT COUNT(*) as c FROM users WHERE referrer_id=?", (uid,), True)
    return r["c"] if r else 0

from datetime import datetime
'''

# ═══ keyboards.py ═══
F["keyboards.py"] = '''\
from aiogram.types import InlineKeyboardMarkup as M, InlineKeyboardButton as B

def main_menu_kb():
    return M(inline_keyboard=[
        [B(text="🛒 Каталог", callback_data="catalog")],
        [B(text="👤 Профиль", callback_data="profile")],
        [B(text="❓ FAQ", callback_data="faq"), B(text="🆘 Поддержка", callback_data="support")],
    ])

def catalog_kb(cats):
    rows = []
    for c in cats:
        rows.append([B(text=f'{c["emoji"]} {c["name"]}', callback_data=f'category:{c["id"]}')])
    rows.append([B(text="◀️ Назад", callback_data="main_menu")])
    return M(inline_keyboard=rows)

def products_kb(prods):
    rows = []
    for p in prods:
        rows.append([B(text=f'{p["emoji"]} {p["name"]} — ${p["price"]}', callback_data=f'product:{p["id"]}')])
    rows.append([B(text="◀️ Назад", callback_data="catalog")])
    return M(inline_keyboard=rows)

def product_kb(pid, stock, price_info=None):
    price = price_info["final_price"] if price_info else 0
    rows = []
    if stock > 0:
        rows.append([B(text=f"💰 Купить за ${price}", callback_data=f"buy:{pid}")])
    else:
        rows.append([B(text="❌ Нет в наличии", callback_data="nope")])
    rows.append([B(text="◀️ Назад", callback_data="catalog")])
    return M(inline_keyboard=rows)

def payment_method_kb(pid):
    return M(inline_keyboard=[
        [B(text="🚀 XRocket", callback_data=f"pay:xrocket:{pid}")],
        [B(text="💰 С баланса", callback_data=f"pay:balance:{pid}")],
        [B(text="💎 USDT TRC20 (вручную)", callback_data=f"pay:manual:{pid}")],
        [B(text="◀️ Назад", callback_data=f"product:{pid}")],
    ])

def profile_kb():
    return M(inline_keyboard=[
        [B(text="💰 Пополнить баланс", callback_data="topup_menu")],
        [B(text="🎁 Активировать промокод", callback_data="promo_use")],
        [B(text="📋 Мои покупки", callback_data="my_orders")],
        [B(text="👥 Рефералка", callback_data="referral")],
        [B(text="◀️ Назад", callback_data="main_menu")],
    ])

def topup_menu_kb():
    return M(inline_keyboard=[
        [B(text="🚀 XRocket", callback_data="topup_method:xrocket")],
        [B(text="💎 USDT TRC20", callback_data="topup_method:manual")],
        [B(text="◀️ Назад", callback_data="profile")],
    ])

def xrocket_amounts_kb():
    return M(inline_keyboard=[
        [B(text="$5", callback_data="topup_amt:xrocket:5"),
         B(text="$10", callback_data="topup_amt:xrocket:10")],
        [B(text="$25", callback_data="topup_amt:xrocket:25"),
         B(text="$50", callback_data="topup_amt:xrocket:50")],
        [B(text="$100", callback_data="topup_amt:xrocket:100")],
        [B(text="◀️ Назад", callback_data="topup_menu")],
    ])

def admin_menu_kb():
    return M(inline_keyboard=[
        [B(text="📁 Категории", callback_data="adm:cats"),
         B(text="📦 Товары", callback_data="adm:prods")],
        [B(text="👥 Юзеры", callback_data="adm:users"),
         B(text="📊 Статистика", callback_data="adm:stats")],
        [B(text="📢 Рассылка", callback_data="adm:broadcast"),
         B(text="💸 Выводы", callback_data="adm:withdraws")],
        [B(text="💳 Ручные топапы", callback_data="adm:topups")],
        [B(text="🔗 Кнопки разделов", callback_data="adm:sbtns"),
         B(text="🎁 Промокоды", callback_data="adm:promos")],
    ])

def admin_cats_kb(cats):
    rows = []
    for c in cats:
        rows.append([B(text=f'{c["emoji"]} {c["name"]}', callback_data=f'adm:cat:{c["id"]}')])
    rows.append([B(text="➕ Добавить", callback_data="adm:cat_add")])
    rows.append([B(text="◀️ Назад", callback_data="adm:back")])
    return M(inline_keyboard=rows)

def admin_cat_kb(cid, name):
    return M(inline_keyboard=[
        [B(text="✏️ Название", callback_data=f"adm:cat_edit:name:{cid}"),
         B(text="😀 Эмодзи", callback_data=f"adm:cat_emoji:{cid}")],
        [B(text="🖼 Картинка", callback_data=f"adm:cat_img:{cid}"),
         B(text="📝 Описание", callback_data=f"adm:cat_edit:desc:{cid}")],
        [B(text="❌ Удалить", callback_data=f"adm:cat_del:{cid}")],
        [B(text="◀️ Назад", callback_data="adm:cats")],
    ])

def admin_prods_kb(prods):
    rows = []
    for p in prods:
        rows.append([B(text=f'{p["emoji"]} {p["name"]} ${p["price"]}', callback_data=f'adm:prod:{p["id"]}')])
    rows.append([B(text="➕ Добавить", callback_data="adm:prod_add")])
    rows.append([B(text="◀️ Назад", callback_data="adm:back")])
    return M(inline_keyboard=rows)

def admin_prod_kb(pid, name):
    return M(inline_keyboard=[
        [B(text="✏️ Название", callback_data=f"adm:prod_edit:name:{pid}"),
         B(text="💲 Цена", callback_data=f"adm:prod_edit:price:{pid}")],
        [B(text="😀 Эмодзи", callback_data=f"adm:prod_emoji:{pid}"),
         B(text="🖼 Картинка", callback_data=f"adm:prod_img:{pid}")],
        [B(text="📝 Описание", callback_data=f"adm:prod_edit:desc:{pid}")],
        [B(text="📋 Айтемы", callback_data=f"adm:prod_items:{pid}"),
         B(text="➕ Айтем", callback_data=f"adm:prod_additem:{pid}")],
        [B(text="❌ Удалить", callback_data=f"adm:prod_del:{pid}")],
        [B(text="◀️ Назад", callback_data="adm:prods")],
    ])

def confirm_kb(prefix, oid):
    return M(inline_keyboard=[
        [B(text="✅ Да", callback_data=f"{prefix}_yes:{oid}"),
         B(text="❌ Нет", callback_data=f"{prefix}_no:{oid}")],
    ])

def back_kb(cb="main_menu"):
    return M(inline_keyboard=[[B(text="◀️ Назад", callback_data=cb)]])

def section_btns_kb(btns):
    rows = []
    for b in btns:
        if b.get("url"):
            rows.append([B(text=b["text"], url=b["url"])])
        elif b.get("callback_data"):
            rows.append([B(text=b["text"], callback_data=b["callback_data"])])
    return rows
'''

# ═══ states.py ═══
F["states.py"] = '''\
from aiogram.fsm.state import State, StatesGroup

class AddCategory(StatesGroup):
    name = State()

class AddProduct(StatesGroup):
    category = State()
    name = State()
    price = State()
    description = State()

class AddItem(StatesGroup):
    value = State()

class EditValue(StatesGroup):
    value = State()

class Broadcast(StatesGroup):
    text = State()

class AddPromocode(StatesGroup):
    code = State()
    ptype = State()
    amount = State()
    discount = State()
    max_uses = State()
    min_purchase = State()
    expires_days = State()

class UsePromocode(StatesGroup):
    code = State()

class AddSectionButton(StatesGroup):
    section = State()
    text = State()
    data = State()

class EditSectionButton(StatesGroup):
    value = State()

class ManualTopUp(StatesGroup):
    amount = State()
    proof = State()

class Withdraw(StatesGroup):
    amount = State()
    wallet = State()
'''

# ═══ handlers/user.py ═══
F["handlers/user.py"] = '''\
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
import database as db
import keyboards as kb
from config import SUPPORT_URL

router = Router()

@router.message(CommandStart())
async def cmd_start(m: Message):
    args = m.text.split()
    ref = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    await db.get_or_create_user(m.from_user.id, m.from_user.username, ref)
    if ref: await db.set_referrer(m.from_user.id, ref)
    btns = await db.sb_list("main_menu")
    txt = "🏠 <b>Главное меню</b>\\n\\nДобро пожаловать в магазин!"
    mk = kb.main_menu_kb()
    extra = kb.section_btns_kb(btns)
    if extra:
        mk.inline_keyboard = extra + mk.inline_keyboard
    await m.answer(txt, reply_markup=mk)

@router.callback_query(F.data == "main_menu")
async def cb_main(c: CallbackQuery):
    btns = await db.sb_list("main_menu")
    mk = kb.main_menu_kb()
    extra = kb.section_btns_kb(btns)
    if extra: mk.inline_keyboard = extra + mk.inline_keyboard
    await c.message.edit_text("🏠 <b>Главное меню</b>", reply_markup=mk)

@router.callback_query(F.data == "catalog")
async def cb_catalog(c: CallbackQuery):
    cats = await db.get_categories()
    if not cats:
        await c.answer("Каталог пуст", show_alert=True); return
    btns = await db.sb_list("catalog")
    mk = kb.catalog_kb(cats)
    extra = kb.section_btns_kb(btns)
    if extra: mk.inline_keyboard = extra + mk.inline_keyboard
    await c.message.edit_text("🛒 <b>Каталог</b>", reply_markup=mk)

@router.callback_query(F.data.startswith("category:"))
async def cb_category(c: CallbackQuery):
    cid = int(c.data.split(":")[1])
    prods = await db.get_products(cid)
    if not prods:
        await c.answer("В этой категории пусто", show_alert=True); return
    await c.message.edit_text(f"📁 <b>Товары</b>", reply_markup=kb.products_kb(prods))

@router.callback_query(F.data.startswith("product:"))
async def cb_product(c: CallbackQuery):
    pid = int(c.data.split(":")[1])
    p = await db.get_product(pid)
    if not p:
        await c.answer("Товар не найден", show_alert=True); return
    stock = await db.get_available_items_count(pid)
    pi = await db.calculate_price_with_promo(c.from_user.id, pid, p["price"])
    txt = f'{p["emoji"]} <b>{p["name"]}</b>\\n\\n'
    if p["description"]: txt += f'{p["description"]}\\n\\n'
    txt += f'💰 Цена: <b>${pi["final_price"]}</b>'
    if pi["discount"] > 0:
        txt += f' <s>${p["price"]}</s>\\n🎁 Скидка: −${pi["discount"]} (<code>{pi["promo_code"]}</code>)'
    txt += f'\\n📦 В наличии: <b>{stock}</b>'
    if p.get("image"):
        try:
            await c.message.delete()
            await c.message.answer_photo(p["image"], txt, reply_markup=kb.product_kb(pid, stock, pi))
        except:
            await c.message.edit_text(txt, reply_markup=kb.product_kb(pid, stock, pi))
    else:
        await c.message.edit_text(txt, reply_markup=kb.product_kb(pid, stock, pi))

@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(c: CallbackQuery):
    pid = int(c.data.split(":")[1])
    p = await db.get_product(pid)
    if not p:
        await c.answer("Товар не найден", show_alert=True); return
    stock = await db.get_available_items_count(pid)
    if stock == 0:
        await c.answer("❌ Товар закончился", show_alert=True); return
    pi = await db.calculate_price_with_promo(c.from_user.id, pid, p["price"])
    txt = f'💳 <b>Оплата</b>\\n\\n{p["emoji"]} {p["name"]}\\n💰 К оплате: <b>${pi["final_price"]}</b>'
    if pi["discount"] > 0:
        txt += f'\\n🎁 Скидка: −${pi["discount"]} (<code>{pi["promo_code"]}</code>)'
    await c.message.edit_text(txt, reply_markup=kb.payment_method_kb(pid))

@router.callback_query(F.data == "profile")
async def cb_profile(c: CallbackQuery):
    u = await db.get_or_create_user(c.from_user.id, c.from_user.username)
    orders = await db.get_user_orders(c.from_user.id)
    ap = await db.get_active_promo(c.from_user.id)
    promo_line = ""
    if ap:
        promo_id, pct = ap
        pr = await db.get_promocode(promo_id=promo_id)
        if pr: promo_line = f'\\n🎁 Активная скидка: <b>{pct}%</b> (<code>{pr["code"]}</code>)'
    txt = (f'👤 <b>Профиль</b>\\n\\n'
           f'🆔 ID: <code>{c.from_user.id}</code>\\n'
           f'💰 Баланс: <b>${u["balance"]:.2f}</b>\\n'
           f'📋 Покупок: <b>{len(orders)}</b>{promo_line}')
    btns = await db.sb_list("profile")
    mk = kb.profile_kb()
    extra = kb.section_btns_kb(btns)
    if extra: mk.inline_keyboard = extra + mk.inline_keyboard
    await c.message.edit_text(txt, reply_markup=mk)

@router.callback_query(F.data == "my_orders")
async def cb_orders(c: CallbackQuery):
    orders = await db.get_user_orders(c.from_user.id)
    if not orders:
        await c.answer("У вас пока нет покупок", show_alert=True); return
    txt = "📋 <b>Мои покупки</b>\\n\\n"
    for o in orders[:10]:
        p = await db.get_product(o["product_id"])
        name = p["name"] if p else "Товар"
        txt += f'• {name} — ${o["price"]} ({o["created_at"][:10]})\\n'
    await c.message.edit_text(txt, reply_markup=kb.back_kb("profile"))

@router.callback_query(F.data == "faq")
async def cb_faq(c: CallbackQuery):
    txt = "❓ <b>FAQ</b>\\n\\n📌 Как купить?\\nВыберите товар → способ оплаты → получите товар.\\n\\n📌 Как пополнить?\\nПрофиль → Пополнить баланс."
    btns = await db.sb_list("faq")
    mk = kb.back_kb("main_menu")
    extra = kb.section_btns_kb(btns)
    if extra: mk.inline_keyboard = extra + mk.inline_keyboard
    await c.message.edit_text(txt, reply_markup=mk)

@router.callback_query(F.data == "support")
async def cb_support(c: CallbackQuery):
    txt = f'🆘 <b>Поддержка</b>\\n\\nНапишите нам: {SUPPORT_URL}'
    btns = await db.sb_list("support")
    mk = kb.back_kb("main_menu")
    extra = kb.section_btns_kb(btns)
    if extra: mk.inline_keyboard = extra + mk.inline_keyboard
    await c.message.edit_text(txt, reply_markup=mk)

@router.callback_query(F.data == "nope")
async def cb_nope(c: CallbackQuery):
    await c.answer("Недоступно", show_alert=True)
'''

# ═══ handlers/payment.py ═══
F["handlers/payment.py"] = '''\
from aiogram import Router, F
from aiogram.types import CallbackQuery
from config import REFERRAL_PERCENT, XROCKET_API_KEY, XROCKET_SHOP_ID
import database as db
import keyboards as kb

router = Router()

async def _di(uid, pid, base):
    i = await db.calculate_price_with_promo(uid, pid, base)
    return i["final_price"], i["discount"], i["promo_code"], i["promo_id"]

async def _fp(uid, promo_id):
    if promo_id:
        await db.use_promocode(promo_id, uid)
        await db.clear_active_promo(uid)

async def _ref(uid, amount, bot):
    ref = await db.get_referrer(uid)
    if ref and REFERRAL_PERCENT > 0:
        bonus = round(amount * REFERRAL_PERCENT / 100, 2)
        await db.add_balance(ref, bonus)
        try:
            await bot.send_message(ref, f"🎉 Реферальный бонус: +${bonus:.2f}")
        except: pass

def _dl(d, c):
    return f'\\n🎁 Скидка: <b>−${d:.2f}</b> (<code>{c}</code>)' if d > 0 and c else ""

@router.callback_query(F.data.startswith("pay:balance:"))
async def cb_pay_balance(c: CallbackQuery, bot):
    pid = int(c.data.split(":")[2])
    p = await db.get_product(pid)
    if not p:
        await c.answer("Товар не найден", show_alert=True); return
    items = await db.get_available_items(pid)
    if not items:
        await c.answer("❌ Нет в наличии", show_alert=True); return
    uid = c.from_user.id
    u = await db.get_user(uid)
    fp, disc, pc, pr_id = await _di(uid, pid, p["price"])
    if u["balance"] < fp:
        await c.answer(f"❌ Недостаточно средств. Нужно ${fp}, на балансе ${u['balance']:.2f}", show_alert=True)
        return
    item = items[0]
    await db.add_balance(uid, -fp)
    oid = await db.create_order(uid, pid, item["id"], fp, "balance", f"bal_{uid}_{pid}")
    await db.mark_item_sold(item["id"], uid)
    await db.update_order_status(oid, "completed")
    await _fp(uid, pr_id)
    await _ref(uid, fp, bot)
    txt = f'✅ <b>Оплата успешна!</b>\\n\\n{p["emoji"]} {p["name"]}\\n💰 Списано: <b>${fp}</b>'
    txt += _dl(disc, pc)
    txt += f'\\n\\n📦 <b>Ваш товар:</b>\\n<code>{item["value"]}</code>'
    await c.message.edit_text(txt, reply_markup=kb.back_kb("main_menu"))

@router.callback_query(F.data.startswith("pay:xrocket:"))
async def cb_pay_xrocket(c: CallbackQuery):
    pid = int(c.data.split(":")[2])
    p = await db.get_product(pid)
    if not p:
        await c.answer("Товар не найден", show_alert=True); return
    items = await db.get_available_items(pid)
    if not items:
        await c.answer("❌ Нет в наличии", show_alert=True); return
    uid = c.from_user.id
    fp, disc, pc, pr_id = await _di(uid, pid, p["price"])
    if not XROCKET_API_KEY:
        await c.answer("❌ XRocket не настроен", show_alert=True); return
    try:
        from xrocket_pay import create_invoice
        inv = await create_invoice(fp, f"Оплата {p['name']}")
        if not inv:
            await c.answer("❌ Ошибка создания счёта", show_alert=True); return
        pay_id = inv["id"]
        if pr_id: pay_id = f"{pay_id}|promo:{pr_id}"
        oid = await db.create_order(uid, pid, items[0]["id"], fp, "xrocket", pay_id)
        await db.create_xrocket_payment(uid, inv["id"], fp, oid)
        txt = f'🚀 <b>Оплата через XRocket</b>\\n\\n💰 Сумма: <b>${fp}</b>'
        txt += _dl(disc, pc)
        txt += f'\\n\\nНажмите кнопку для оплаты:'
        from aiogram.types import InlineKeyboardMarkup as M, InlineKeyboardButton as B
        mk = M(inline_keyboard=[
            [B(text="💳 Оплатить", url=inv["url"])],
            [B(text="✅ Проверить оплату", callback_data=f"xr_check:{inv['id']}")],
            [B(text="◀️ Назад", callback_data=f"buy:{pid}")],
        ])
        await c.message.edit_text(txt, reply_markup=mk)
    except Exception as e:
        await c.answer(f"❌ Ошибка: {e}", show_alert=True)

@router.callback_query(F.data.startswith("pay:manual:"))
async def cb_pay_manual(c: CallbackQuery):
    pid = int(c.data.split(":")[2])
    p = await db.get_product(pid)
    if not p:
        await c.answer("Товар не найден", show_alert=True); return
    items = await db.get_available_items(pid)
    if not items:
        await c.answer("❌ Нет в наличии", show_alert=True); return
    uid = c.from_user.id
    fp, disc, pc, pr_id = await _di(uid, pid, p["price"])
    txt = (f'💎 <b>Оплата USDT TRC20</b>\\n\\n'
           f'💰 Сумма: <b>${fp}</b>\\n'
           f'📝 Назначение: <code>ORDER_{uid}_{pid}</code>')
    txt += _dl(disc, pc)
    txt += (f'\\n\\n1. Переведите ${fp} USDT на кошелёк:\\n'
            f'<code>YOUR_USDT_WALLET</code>\\n\\n'
            f'2. После оплаты нажмите "Проверить"')
    from aiogram.types import InlineKeyboardMarkup as M, InlineKeyboardButton as B
    mk = M(inline_keyboard=[
        [B(text="✅ Я оплатил", callback_data=f"manual_check:{pid}:{fp}:{pr_id or 0}")],
        [B(text="◀️ Назад", callback_data=f"buy:{pid}")],
    ])
    await c.message.edit_text(txt, reply_markup=mk)

@router.callback_query(F.data.startswith("manual_check:"))
async def cb_manual_check(c: CallbackQuery, bot):
    parts = c.data.split(":")
    pid = int(parts[1])
    fp = float(parts[2])
    pr_id = int(parts[3]) if len(parts) > 3 and parts[3] != "0" else None
    p = await db.get_product(pid)
    if not p:
        await c.answer("Товар не найден", show_alert=True); return
    items = await db.get_available_items(pid)
    if not items:
        await c.answer("❌ Нет в наличии", show_alert=True); return
    uid = c.from_user.id
    item = items[0]
    oid = await db.create_order(uid, pid, item["id"], fp, "manual_usdt", f"manual_{uid}_{pid}")
    await db.mark_item_sold(item["id"], uid)
    await db.update_order_status(oid, "completed")
    await _fp(uid, pr_id)
    await _ref(uid, fp, bot)
    txt = f'✅ <b>Заявка принята!</b>\\n\\nТовар будет выдан после подтверждения оплаты админом.\\n📦 Заказ #{oid}'
    await c.message.edit_text(txt, reply_markup=kb.back_kb("main_menu"))
'''

# ═══ handlers/promocodes.py (НОВЫЙ) ═══
F["handlers/promocodes.py"] = '''\
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime, timedelta
from config import ADMIN_IDS
import database as db
import keyboards as kb
from states import AddPromocode, UsePromocode

router = Router()

def is_admin(uid): return uid in ADMIN_IDS

# ── Юзер: активация промокода ──
@router.message(Command("promo"))
async def cmd_promo(m: Message):
    args = m.text.split()
    if len(args) < 2:
        await m.answer("Использование: /promo КОД")
        return
    await db.get_or_create_user(m.from_user.id, m.from_user.username)
    res = await db.apply_promocode(args[1], m.from_user.id)
    if res["ok"]:
        if res["type"] == "balance":
            await m.answer(f"✅ Промокод активирован!\\n💰 На баланс зачислено: <b>${res['amount']}</b>")
        else:
            await m.answer(f"✅ Промокод активирован!\\n🎁 Скидка <b>{res['discount']}%</b> применена к следующей покупке.")
    else:
        await m.answer(f"❌ {res['error']}")

@router.callback_query(F.data == "promo_use")
async def cb_promo_use(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("🎁 Введите промокод:", reply_markup=kb.back_kb("profile"))
    await state.set_state(UsePromocode.code)

@router.message(UsePromocode.code)
async def fsm_promo_code(m: Message, state: FSMContext):
    await state.clear()
    await db.get_or_create_user(m.from_user.id, m.from_user.username)
    res = await db.apply_promocode(m.text.strip(), m.from_user.id)
    if res["ok"]:
        if res["type"] == "balance":
            await m.answer(f"✅ Промокод активирован!\\n💰 +${res['amount']} на баланс")
        else:
            await m.answer(f"✅ Скидка <b>{res['discount']}%</b> применена!")
    else:
        await m.answer(f"❌ {res['error']}")

# ── Админ: промокоды ──
@router.callback_query(F.data == "adm:promos")
async def adm_promos(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    promos = await db.get_promocodes()
    txt = "🎁 <b>Промокоды</b>\\n\\n"
    if not promos:
        txt += "Пока нет промокодов."
    else:
        for p in promos[:15]:
            st = "🟢" if p["is_active"] else "🔴"
            tp = f"+${p['amount']}" if p["type"] == "balance" else f"{p['discount_percent']}%"
            txt += f'{st} <code>{p["code"]}</code> — {tp} ({p["uses_count"]}/{p["max_uses"] or "∞"})\\n'
    from aiogram.types import InlineKeyboardMarkup as M, InlineKeyboardButton as B
    mk = M(inline_keyboard=[
        [B(text="➕ Создать", callback_data="adm:promo_add")],
        [B(text="◀️ Назад", callback_data="adm:back")],
    ])
    await c.message.edit_text(txt, reply_markup=mk)

@router.callback_query(F.data == "adm:promo_add")
async def adm_promo_add(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return
    await c.message.edit_text("Введите код промокода (латиница/цифры):")
    await state.set_state(AddPromocode.code)

@router.message(AddPromocode.code)
async def fsm_pcode(m: Message, state: FSMContext):
    await state.update_data(code=m.text.strip().upper())
    from aiogram.types import InlineKeyboardMarkup as M, InlineKeyboardButton as B
    mk = M(inline_keyboard=[
        [B(text="💰 На баланс", callback_data="pt:balance"),
         B(text="🏷 Скидка %", callback_data="pt:discount")],
    ])
    await m.answer("Тип промокода:", reply_markup=mk)
    await state.set_state(AddPromocode.ptype)

@router.callback_query(F.data.startswith("pt:"))
async def cb_ptype(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return
    ptype = c.data.split(":")[1]
    await state.update_data(ptype=ptype)
    if ptype == "balance":
        await c.message.edit_text("Введите сумму на баланс ($):")
        await state.set_state(AddPromocode.amount)
    else:
        await c.message.edit_text("Введите процент скидки (1-100):")
        await state.set_state(AddPromocode.discount)

@router.message(AddPromocode.amount)
async def fsm_pamount(m: Message, state: FSMContext):
    try:
        val = float(m.text)
    except:
        await m.answer("Введите число!"); return
    await state.update_data(amount=val, discount=0)
    await m.answer("Макс. использований (0 = безлимит):")
    await state.set_state(AddPromocode.max_uses)

@router.message(AddPromocode.discount)
async def fsm_pdiscount(m: Message, state: FSMContext):
    try:
        val = float(m.text)
    except:
        await m.answer("Введите число!"); return
    await state.update_data(amount=0, discount=val)
    await m.answer("Макс. использований (0 = безлимит):")
    await state.set_state(AddPromocode.max_uses)

@router.message(AddPromocode.max_uses)
async def fsm_pmax(m: Message, state: FSMContext):
    try:
        val = int(m.text)
    except:
        await m.answer("Введите число!"); return
    await state.update_data(max_uses=val)
    await m.answer("Мин. сумма покупки (0 = без ограничений):")
    await state.set_state(AddPromocode.min_purchase)

@router.message(AddPromocode.min_purchase)
async def fsm_pmin(m: Message, state: FSMContext):
    try:
        val = float(m.text)
    except:
        await m.answer("Введите число!"); return
    await state.update_data(min_purchase=val)
    await m.answer("Срок действия в днях (0 = бессрочно):")
    await state.set_state(AddPromocode.expires_days)

@router.message(AddPromocode.expires_days)
async def fsm_pexp(m: Message, state: FSMContext):
    try:
        days = int(m.text)
    except:
        await m.answer("Введите число!"); return
    data = await state.get_data()
    await state.clear()
    exp = None
    if days > 0:
        exp = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    await db.create_promocode(
        code=data["code"], ptype=data["ptype"],
        amount=data.get("amount", 0), discount=data.get("discount", 0),
        max_uses=data.get("max_uses", 0), min_purchase=data.get("min_purchase", 0),
        expires_at=exp, created_by=m.from_user.id)
    tp = f"+${data.get('amount',0)}" if data["ptype"] == "balance" else f"{data.get('discount',0)}%"
    await m.answer(f"✅ Промокод <code>{data['code']}</code> создан!\\nТип: {tp}")
'''

# ═══ handlers/section_buttons.py (НОВЫЙ) ═══
F["handlers/section_buttons.py"] = '''\
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from config import ADMIN_IDS
import database as db
import keyboards as kb
from states import AddSectionButton, EditSectionButton

router = Router()
SECTIONS = {"main_menu": "🏠 Главное", "profile": "👤 Профиль",
            "catalog": "🛒 Каталог", "faq": "❓ FAQ",
            "support": "🆘 Поддержка", "referral": "👥 Рефералка"}

def is_admin(uid): return uid in ADMIN_IDS

@router.callback_query(F.data == "adm:sbtns")
async def adm_sbtns(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    from aiogram.types import InlineKeyboardMarkup as M, InlineKeyboardButton as B
    rows = []
    for k, v in SECTIONS.items():
        cnt = len(await db.sb_list(k))
        rows.append([B(text=f"{v} ({cnt})", callback_data=f"adm:sb_sec:{k}")])
    rows.append([B(text="◀️ Назад", callback_data="adm:back")])
    await c.message.edit_text("🔗 <b>Кнопки разделов</b>", reply_markup=M(inline_keyboard=rows))

@router.callback_query(F.data.startswith("adm:sb_sec:"))
async def adm_sb_sec(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    sec = c.data.split(":")[2]
    btns = await db.sb_list(sec)
    all_btns = await db._q("SELECT * FROM section_buttons WHERE section=? ORDER BY sort_order", (sec,))
    txt = f"🔗 <b>{SECTIONS.get(sec, sec)}</b>\\n\\n"
    if not all_btns:
        txt += "Нет кнопок."
    else:
        for b in all_btns:
            st = "🟢" if b["is_active"] else "🔴"
            lnk = b["url"] or b["callback_data"] or "—"
            txt += f'{st} {b["text"]} → <code>{lnk}</code>\\n'
    from aiogram.types import InlineKeyboardMarkup as M, InlineKeyboardButton as B
    rows = []
    for b in all_btns:
        rows.append([B(text=f'{"✅" if b["is_active"] else "⬜"} {b["text"]}', callback_data=f"adm:sb:{b['id']}")])
    rows.append([B(text="➕ Добавить", callback_data=f"adm:sb_add:{sec}")])
    rows.append([B(text="◀️ Назад", callback_data="adm:sbtns")])
    await c.message.edit_text(txt, reply_markup=M(inline_keyboard=rows))

@router.callback_query(F.data.startswith("adm:sb_add:"))
async def adm_sb_add(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return
    sec = c.data.split(":")[2]
    await state.update_data(section=sec)
    await c.message.edit_text(f"Введите текст кнопки для {SECTIONS.get(sec, sec)}:")
    await state.set_state(AddSectionButton.text)

@router.message(AddSectionButton.text)
async def fsm_sb_text(m: Message, state: FSMContext):
    await state.update_data(text=m.text.strip())
    await m.answer("Введите URL или callback_data (начните с http для URL):")
    await state.set_state(AddSectionButton.data)

@router.message(AddSectionButton.data)
async def fsm_sb_data(m: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    val = m.text.strip()
    url = val if val.startswith("http") else None
    cb = val if not val.startswith("http") else None
    await db.sb_add(data["section"], data["text"], url, cb)
    await m.answer(f"✅ Кнопка «{data['text']}» добавлена!")

@router.callback_query(F.data.startswith("adm:sb:"))
async def adm_sb_one(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    sid = int(c.data.split(":")[2])
    b = await db.sb_get(sid)
    if not b:
        await c.answer("Не найдено", show_alert=True); return
    lnk = b["url"] or b["callback_data"] or "—"
    txt = f'🔗 Кнопка: <b>{b["text"]}</b>\\nСсылка: <code>{lnk}</code>\\nСтатус: {"🟢" if b["is_active"] else "🔴"}'
    from aiogram.types import InlineKeyboardMarkup as M, InlineKeyboardButton as B
    mk = M(inline_keyboard=[
        [B(text="🔄 Вкл/Выкл", callback_data=f"adm:sb_tog:{sid}"),
         B(text="❌ Удалить", callback_data=f"adm:sb_del:{sid}")],
        [B(text="◀️ Назад", callback_data=f"adm:sb_sec:{b['section']}")],
    ])
    await c.message.edit_text(txt, reply_markup=mk)

@router.callback_query(F.data.startswith("adm:sb_tog:"))
async def adm_sb_tog(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    sid = int(c.data.split(":")[2])
    await db.sb_toggle(sid)
    b = await db.sb_get(sid)
    await c.answer("Переключено")
    if b:
        from aiogram.types import InlineKeyboardMarkup as M, InlineKeyboardButton as B
        lnk = b["url"] or b["callback_data"] or "—"
        txt = f'🔗 Кнопка: <b>{b["text"]}</b>\\nСсылка: <code>{lnk}</code>\\nСтатус: {"🟢" if b["is_active"] else "🔴"}'
        mk = M(inline_keyboard=[
            [B(text="🔄 Вкл/Выкл", callback_data=f"adm:sb_tog:{sid}"),
             B(text="❌ Удалить", callback_data=f"adm:sb_del:{sid}")],
            [B(text="◀️ Назад", callback_data=f"adm:sb_sec:{b['section']}")],
        ])
        await c.message.edit_text(txt, reply_markup=mk)

@router.callback_query(F.data.startswith("adm:sb_del:"))
async def adm_sb_del(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    sid = int(c.data.split(":")[2])
    b = await db.sb_get(sid)
    sec = b["section"] if b else "main_menu"
    await db.sb_delete(sid)
    await c.answer("Удалено")
    # вернуться к списку секции
    btns = await db._q("SELECT * FROM section_buttons WHERE section=? ORDER BY sort_order", (sec,))
    txt = f"🔗 <b>{SECTIONS.get(sec, sec)}</b>\\n\\n"
    if not btns: txt += "Нет кнопок."
    from aiogram.types import InlineKeyboardMarkup as M, InlineKeyboardButton as B
    rows = []
    for b in (btns or []):
        rows.append([B(text=f'{"✅" if b["is_active"] else "⬜"} {b["text"]}', callback_data=f"adm:sb:{b['id']}")])
    rows.append([B(text="➕ Добавить", callback_data=f"adm:sb_add:{sec}")])
    rows.append([B(text="◀️ Назад", callback_data="adm:sbtns")])
    await c.message.edit_text(txt, reply_markup=M(inline_keyboard=rows))
'''

# ═══ handlers/topup.py (НОВЫЙ) ═══
F["handlers/topup.py"] = '''\
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
import database as db
import keyboards as kb
from states import ManualTopUp
from config import XROCKET_API_KEY

router = Router()

@router.callback_query(F.data == "topup_menu")
async def cb_topup_menu(c: CallbackQuery):
    await c.message.edit_text("💰 <b>Пополнение баланса</b>\\n\\nВыберите способ:", reply_markup=kb.topup_menu_kb())

@router.callback_query(F.data == "topup_method:xrocket")
async def cb_topup_xr(c: CallbackQuery):
    if not XROCKET_API_KEY:
        await c.answer("❌ XRocket не настроен", show_alert=True); return
    await c.message.edit_text("💰 Выберите сумму пополнения:", reply_markup=kb.xrocket_amounts_kb())

@router.callback_query(F.data.startswith("topup_amt:xrocket:"))
async def cb_topup_xr_amt(c: CallbackQuery):
    amt = float(c.data.split(":")[2])
    try:
        from xrocket_pay import create_invoice
        inv = await create_invoice(amt, "Пополнение баланса")
        if not inv:
            await c.answer("❌ Ошибка", show_alert=True); return
        await db.create_xrocket_payment(c.from_user.id, inv["id"], amt)
        from aiogram.types import InlineKeyboardMarkup as M, InlineKeyboardButton as B
        mk = M(inline_keyboard=[
            [B(text="💳 Оплатить", url=inv["url"])],
            [B(text="✅ Проверить", callback_data=f"topup_check:xrocket:{inv['id']}")],
            [B(text="◀️ Назад", callback_data="topup_menu")],
        ])
        await c.message.edit_text(f"🚀 Пополнение на <b>${amt}</b>\\n\\nНажмите «Оплатить»:", reply_markup=mk)
    except Exception as e:
        await c.answer(f"❌ {e}", show_alert=True)

@router.callback_query(F.data.startswith("topup_check:xrocket:"))
async def cb_topup_xr_check(c: CallbackQuery, bot):
    inv_id = c.data.split(":")[2]
    pay = await db.get_xrocket_payment(inv_id)
    if not pay:
        await c.answer("Платёж не найден", show_alert=True); return
    if pay["status"] == "paid":
        await c.answer("✅ Уже зачислено!", show_alert=True); return
    try:
        from xrocket_pay import check_invoice
        status = await check_invoice(inv_id)
        if status == "paid":
            await db.update_xrocket_payment(inv_id, "paid")
            await db.add_balance(c.from_user.id, pay["amount"])
            await c.message.edit_text(f"✅ Баланс пополнен на <b>${pay['amount']}</b>!")
        else:
            await c.answer("⏳ Оплата ещё не получена", show_alert=True)
    except:
        await c.answer("⏳ Не удалось проверить", show_alert=True)

@router.callback_query(F.data == "topup_method:manual")
async def cb_topup_manual(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("💎 <b>Пополнение USDT TRC20</b>\\n\\nВведите сумму ($):", reply_markup=kb.back_kb("topup_menu"))
    await state.set_state(ManualTopUp.amount)

@router.message(ManualTopUp.amount)
async def fsm_topup_amt(m: Message, state: FSMContext):
    try:
        amt = float(m.text)
        if amt < 1: raise ValueError
    except:
        await m.answer("Введите сумму от $1"); return
    await state.update_data(amount=amt)
    await m.answer(
        f"📤 Переведите <b>${amt}</b> USDT TRC20 на:\\n"
        f"<code>YOUR_USDT_WALLET</code>\\n\\n"
        f"После оплаты отправьте скриншот/фото чека:")
    await state.set_state(ManualTopUp.proof)

@router.message(ManualTopUp.proof, F.photo)
async def fsm_topup_proof(m: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    photo = m.photo[-1].file_id
    tid = await db.create_manual_topup(m.from_user.id, data["amount"], "", photo)
    await m.answer(f"✅ Заявка #{tid} на <b>${data['amount']}</b> отправлена!\\n⏳ Ожидайте подтверждения.")
    # уведомить админов
    from config import ADMIN_IDS
    for aid in ADMIN_IDS:
        try:
            from aiogram.types import InlineKeyboardMarkup as M, InlineKeyboardButton as B
            mk = M(inline_keyboard=[
                [B(text="✅ Одобрить", callback_data=f"adm:topup_approve:{tid}"),
                 B(text="❌ Отклонить", callback_data=f"adm:topup_reject:{tid}")],
            ])
            await m.bot.send_photo(aid, photo,
                caption=f"💳 Новый топап #{tid}\\n👤 {m.from_user.id}\\n💰 ${data['amount']}",
                reply_markup=mk)
        except: pass

@router.message(ManualTopUp.proof)
async def fsm_topup_proof_text(m: Message):
    await m.answer("Отправьте фото/скриншот чека!")
'''

# ═══ handlers/admin.py ═══
F["handlers/admin.py"] = '''\
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from config import ADMIN_IDS
import database as db
import keyboards as kb
from states import AddCategory, AddProduct, AddItem, EditValue, Broadcast

router = Router()
def is_admin(uid): return uid in ADMIN_IDS

@router.message(Command("admin"))
async def cmd_admin(m: Message):
    if not is_admin(m.from_user.id): return
    await m.answer("⚙️ <b>Админ-панель</b>", reply_markup=kb.admin_menu_kb())

@router.callback_query(F.data == "adm:back")
async def adm_back(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    await c.message.edit_text("⚙️ <b>Админ-панель</b>", reply_markup=kb.admin_menu_kb())

# ── Категории ──
@router.callback_query(F.data == "adm:cats")
async def adm_cats(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    cats = await db.get_all_categories()
    await c.message.edit_text("📁 <b>Категории</b>", reply_markup=kb.admin_cats_kb(cats))

@router.callback_query(F.data == "adm:cat_add")
async def adm_cat_add(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return
    await c.message.edit_text("Введите название категории:")
    await state.set_state(AddCategory.name)

@router.message(AddCategory.name)
async def fsm_cat_name(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    await state.clear()
    cid = await db.create_category(m.text.strip())
    await m.answer(f"✅ Категория «{m.text.strip()}» создана!")

@router.callback_query(F.data.startswith("adm:cat:"))
async def adm_cat(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    cid = int(c.data.split(":")[2])
    cat = await db.get_category(cid)
    if not cat:
        await c.answer("Не найдено", show_alert=True); return
    txt = f'{cat["emoji"]} <b>{cat["name"]}</b>\\n\\n'
    if cat.get("description"): txt += f'{cat["description"]}\\n'
    await c.message.edit_text(txt, reply_markup=kb.admin_cat_kb(cid, cat["name"]))

@router.callback_query(F.data.startswith("adm:cat_edit:"))
async def adm_cat_edit(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return
    parts = c.data.split(":")
    field, cid = parts[2], parts[3]
    await state.update_data(edit_target="cat", edit_field=field, edit_id=cid)
    labels = {"name": "название", "desc": "описание"}
    await c.message.edit_text(f"Введите новое {labels.get(field, field)}:")
    await state.set_state(EditValue.value)

@router.callback_query(F.data.startswith("adm:cat_del:"))
async def adm_cat_del(c: CallbackQuery):
    if not is_admin(c