import aiosqlite
from datetime import datetime
from typing import Optional

DB_PATH = "shop.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
                balance REAL DEFAULT 0, ref_balance REAL DEFAULT 0,
                total_spent REAL DEFAULT 0, total_earned REAL DEFAULT 0,
                referrer_id INTEGER, referrals_count INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now')));
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                description TEXT DEFAULT '', emoji TEXT DEFAULT '📦',
                image_id TEXT, is_active INTEGER DEFAULT 1, sort_order INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER,
                name TEXT NOT NULL, description TEXT DEFAULT '', price REAL NOT NULL,
                image_id TEXT, is_active INTEGER DEFAULT 1, created_at TEXT DEFAULT (datetime('now')));
            CREATE TABLE IF NOT EXISTS product_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER,
                content TEXT NOT NULL, is_sold INTEGER DEFAULT 0, sold_to INTEGER, sold_at TEXT);
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                product_id INTEGER, item_id INTEGER, amount REAL,
                payment_method TEXT, payment_id TEXT, status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now')), completed_at TEXT);
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                amount REAL, method TEXT, address TEXT, status TEXT DEFAULT 'pending',
                admin_comment TEXT, created_at TEXT DEFAULT (datetime('now')), processed_at TEXT);
            CREATE TABLE IF NOT EXISTS manual_topups (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                amount REAL, tx_hash TEXT, photo_id TEXT, status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now')), processed_at TEXT, product_id INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS sub_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER UNIQUE,
                username TEXT, title TEXT, invite_link TEXT,
                is_active INTEGER DEFAULT 1, created_at TEXT DEFAULT (datetime('now')));
            CREATE TABLE IF NOT EXISTS promocodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL,
                type TEXT DEFAULT 'balance', amount REAL DEFAULT 0,
                discount_percent INTEGER DEFAULT 0, max_uses INTEGER DEFAULT 1,
                uses_count INTEGER DEFAULT 0, min_purchase REAL DEFAULT 0,
                product_id INTEGER DEFAULT 0, category_id INTEGER DEFAULT 0,
                expires_at TEXT, is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')), created_by INTEGER);
            CREATE TABLE IF NOT EXISTS promocode_uses (
                id INTEGER PRIMARY KEY AUTOINCREMENT, promocode_id INTEGER,
                user_id INTEGER, used_at TEXT DEFAULT (datetime('now')),
                UNIQUE(promocode_id, user_id));
            CREATE TABLE IF NOT EXISTS section_buttons (
                id INTEGER PRIMARY KEY AUTOINCREMENT, section TEXT NOT NULL,
                text TEXT NOT NULL, url TEXT, callback_data TEXT,
                sort_order INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')));
        """)
        await db.commit()
        for k, v in {"welcome_text": "👋 Добро пожаловать, <b>{name}</b>!",
                      "welcome_image": "", "profile_image": "",
                      "faq_text": "ℹ️ <b>FAQ</b>", "faq_image": "",
                      "support_text": "💬 <b>Поддержка</b>\n@your_support"}.items():
            await db.execute("INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)", (k, v))
        await db.commit()

async def get_setting(key, default=""):
    async with aiosqlite.connect(DB_PATH) as db:
        r = await (await db.execute("SELECT value FROM settings WHERE key=?", (key,))).fetchone()
        return r[0] if r else default

async def set_setting(key, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=?", (key, value, value))
        await db.commit()

async def get_setting_bool(key, default=False):
    v = await get_setting(key)
    return str(v).strip().lower() in ("1","true","yes","on") if v else default

async def get_or_create_user(user_id, username=None, first_name=None, referrer_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        user = await cur.fetchone()
        if not user:
            vr = None
            if referrer_id and referrer_id != user_id:
                if await (await db.execute("SELECT 1 FROM users WHERE user_id=?", (referrer_id,))).fetchone():
                    vr = referrer_id
            await db.execute("INSERT INTO users (user_id,username,first_name,referrer_id) VALUES (?,?,?,?)", (user_id, username, first_name, vr))
            if vr:
                await db.execute("UPDATE users SET referrals_count=referrals_count+1 WHERE user_id=?", (vr,))
            await db.commit()
            return dict(await (await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))).fetchone()), True
        await db.execute("UPDATE users SET username=?, first_name=? WHERE user_id=?", (username, first_name, user_id))
        await db.commit()
        return dict(user), False

async def get_user(uid):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        r = await (await db.execute("SELECT * FROM users WHERE user_id=?", (uid,))).fetchone()
        return dict(r) if r else None

async def get_user_count():
    async with aiosqlite.connect(DB_PATH) as db:
        return (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]

async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await db.execute("SELECT * FROM users WHERE is_banned=0")).fetchall()]

async def ban_user(uid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (uid,)); await db.commit()

async def unban_user(uid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (uid,)); await db.commit()

async def add_balance(uid, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, uid)); await db.commit()

async def subtract_balance(uid, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        r = await (await db.execute("SELECT balance FROM users WHERE user_id=?", (uid,))).fetchone()
        if not r or r[0] < amount: return False
        await db.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amount, uid)); await db.commit()
        return True

async def add_ref_balance(uid, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET ref_balance=ref_balance+?, total_earned=total_earned+? WHERE user_id=?", (amount, amount, uid)); await db.commit()

async def subtract_ref_balance(uid, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        r = await (await db.execute("SELECT ref_balance FROM users WHERE user_id=?", (uid,))).fetchone()
        if not r or r[0] < amount: return False
        await db.execute("UPDATE users SET ref_balance=ref_balance-? WHERE user_id=?", (amount, uid)); await db.commit()
        return True

async def get_categories(active_only=True):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        q = "SELECT * FROM categories" + (" WHERE is_active=1" if active_only else "") + " ORDER BY sort_order,id"
        return [dict(r) for r in await (await db.execute(q)).fetchall()]

async def get_category(cid):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        r = await (await db.execute("SELECT * FROM categories WHERE id=?", (cid,))).fetchone()
        return dict(r) if r else None

async def add_category(name, description="", emoji="📦", image_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("INSERT INTO categories (name,description,emoji,image_id) VALUES (?,?,?,?)", (name, description, emoji, image_id))
        await db.commit(); return cur.lastrowid

async def update_category(cid, **kw):
    if not kw: return
    f = ", ".join(f"{k}=?" for k in kw)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE categories SET {f} WHERE id=?", list(kw.values())+[cid]); await db.commit()

async def delete_category(cid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM product_items WHERE product_id IN (SELECT id FROM products WHERE category_id=?)", (cid,))
        await db.execute("DELETE FROM products WHERE category_id=?", (cid,))
        await db.execute("DELETE FROM categories WHERE id=?", (cid,)); await db.commit()

async def get_products(cat_id, active_only=True):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        q = "SELECT * FROM products WHERE category_id=?" + (" AND is_active=1" if active_only else "")
        return [dict(r) for r in await (await db.execute(q, (cat_id,))).fetchall()]

async def get_product(pid):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        r = await (await db.execute("SELECT * FROM products WHERE id=?", (pid,))).fetchone()
        return dict(r) if r else None

async def add_product(cat_id, name, desc, price, image_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("INSERT INTO products (category_id,name,description,price,image_id) VALUES (?,?,?,?,?)", (cat_id, name, desc, price, image_id))
        await db.commit(); return cur.lastrowid

async def update_product(pid, **kw):
    if not kw: return
    f = ", ".join(f"{k}=?" for k in kw)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE products SET {f} WHERE id=?", list(kw.values())+[pid]); await db.commit()

async def delete_product(pid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM product_items WHERE product_id=?", (pid,))
        await db.execute("DELETE FROM products WHERE id=?", (pid,)); await db.commit()

async def get_available_items_count(pid):
    async with aiosqlite.connect(DB_PATH) as db:
        return (await (await db.execute("SELECT COUNT(*) FROM product_items WHERE product_id=? AND is_sold=0", (pid,))).fetchone())[0]

async def add_items(pid, items):
    async with aiosqlite.connect(DB_PATH) as db:
        for it in items:
            if it.strip():
                await db.execute("INSERT INTO product_items (product_id,content) VALUES (?,?)", (pid, it.strip()))
        await db.commit()

async def buy_item(pid, uid):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        item = await (await db.execute("SELECT * FROM product_items WHERE product_id=? AND is_sold=0 LIMIT 1", (pid,))).fetchone()
        if not item: return None
        item = dict(item)
        await db.execute("UPDATE product_items SET is_sold=1, sold_to=?, sold_at=? WHERE id=?", (uid, datetime.now().isoformat(), item["id"]))
        prod = await get_product(pid)
        if prod:
            await db.execute("UPDATE users SET total_spent=total_spent+? WHERE user_id=?", (prod["price"], uid))
        await db.commit()
        return item["id"], item["content"]

async def create_order(uid, pid, amount, method, pay_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("INSERT INTO orders (user_id,product_id,amount,payment_method,payment_id) VALUES (?,?,?,?,?)", (uid, pid, amount, method, pay_id))
        await db.commit(); return cur.lastrowid

async def complete_order(oid, item_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET status='completed', item_id=?, completed_at=? WHERE id=?", (item_id, datetime.now().isoformat(), oid)); await db.commit()

async def get_order_by_payment(pay_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        r = await (await db.execute("SELECT * FROM orders WHERE payment_id=?", (pay_id,))).fetchone()
        return dict(r) if r else None

async def get_order_by_payment_prefix(prefix):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        r = await (await db.execute("SELECT * FROM orders WHERE payment_id LIKE ? AND status='pending' ORDER BY id DESC LIMIT 1", (f"{prefix}%",))).fetchone()
        return dict(r) if r else None

async def get_orders_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        r = await (await db.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM orders WHERE status='completed'")).fetchone()
        return {"count": r[0], "total": r[1]}

async def get_user_orders(uid, limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await db.execute("SELECT o.*, p.name as product_name FROM orders o LEFT JOIN products p ON o.product_id=p.id WHERE o.user_id=? AND o.status='completed' ORDER BY o.created_at DESC LIMIT ?", (uid, limit))).fetchall()]

async def get_user_referrals(uid):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await db.execute("SELECT * FROM users WHERE referrer_id=? ORDER BY created_at DESC", (uid,))).fetchall()]

async def create_withdrawal(uid, amount, method, address):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("INSERT INTO withdrawals (user_id,amount,method,address) VALUES (?,?,?,?)", (uid, amount, method, address))
        await db.commit(); return cur.lastrowid

async def get_withdrawal(wid):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        r = await (await db.execute("SELECT * FROM withdrawals WHERE id=?", (wid,))).fetchone()
        return dict(r) if r else None

async def update_withdrawal(wid, status, comment=""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE withdrawals SET status=?, admin_comment=?, processed_at=? WHERE id=?", (status, comment, datetime.now().isoformat(), wid)); await db.commit()

async def get_pending_withdrawals():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await db.execute("SELECT * FROM withdrawals WHERE status='pending' ORDER BY created_at")).fetchall()]

async def get_user_withdrawals(uid, limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await db.execute("SELECT * FROM withdrawals WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (uid, limit))).fetchall()]

async def create_manual_topup(uid, amount, tx_hash="", photo_id=None, product_id=0):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("INSERT INTO manual_topups (user_id,amount,tx_hash,photo_id,product_id) VALUES (?,?,?,?,?)", (uid, amount, tx_hash, photo_id, int(product_id or 0)))
        await db.commit(); return cur.lastrowid

async def get_manual_topup(mid):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        r = await (await db.execute("SELECT * FROM manual_topups WHERE id=?", (mid,))).fetchone()
        return dict(r) if r else None

async def get_pending_manual_topups():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await db.execute("SELECT * FROM manual_topups WHERE status='pending' ORDER BY created_at")).fetchall()]

async def update_manual_topup(mid, status):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE manual_topups SET status=?, processed_at=? WHERE id=?", (status, datetime.now().isoformat(), mid)); await db.commit()

async def add_sub_channel(chat_id, username=None, title=None, invite_link=None):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            cur = await db.execute("INSERT INTO sub_channels (chat_id,username,title,invite_link) VALUES (?,?,?,?)", (int(chat_id), username, title, invite_link))
            await db.commit(); return cur.lastrowid
        except Exception:
            await db.execute("UPDATE sub_channels SET username=?, title=?, invite_link=COALESCE(?,invite_link), is_active=1 WHERE chat_id=?", (username, title, invite_link, int(chat_id)))
            await db.commit()
            r = await (await db.execute("SELECT id FROM sub_channels WHERE chat_id=?", (int(chat_id),))).fetchone()
            return r[0] if r else None

async def get_sub_channels():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await db.execute("SELECT * FROM sub_channels ORDER BY id")).fetchall()]

async def get_active_sub_channels():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await db.execute("SELECT * FROM sub_channels WHERE is_active=1 ORDER BY id")).fetchall()]

async def get_sub_channel(cid):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        r = await (await db.execute("SELECT * FROM sub_channels WHERE id=?", (cid,))).fetchone()
        return dict(r) if r else None

async def toggle_sub_channel(cid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE sub_channels SET is_active=CASE is_active WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (cid,)); await db.commit()

async def delete_sub_channel(cid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM sub_channels WHERE id=?", (cid,)); await db.commit()

async def update_sub_invite(cid, link):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE sub_channels SET invite_link=? WHERE id=?", (link, cid)); await db.commit()

async def deactivate_sub_channel_by_chat(chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE sub_channels SET is_active=0 WHERE chat_id=?", (int(chat_id),)); await db.commit()

async def create_promocode(code, type_="balance", amount=0, discount_percent=0, max_uses=1, min_purchase=0, product_id=0, category_id=0, expires_at=None, created_by=0):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            cur = await db.execute("INSERT INTO promocodes (code,type,amount,discount_percent,max_uses,min_purchase,product_id,category_id,expires_at,created_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (code.upper(), type_, amount, discount_percent, max_uses, min_purchase, product_id, category_id, expires_at, created_by))
            await db.commit(); return cur.lastrowid
        except Exception: return None

async def get_promocode(code=None, promo_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if code: r = await (await db.execute("SELECT * FROM promocodes WHERE code=?", (code.upper(),))).fetchone()
        else: r = await (await db.execute("SELECT * FROM promocodes WHERE id=?", (promo_id,))).fetchone()
        return dict(r) if r else None

async def get_all_promocodes():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await db.execute("SELECT * FROM promocodes ORDER BY id DESC")).fetchall()]

async def delete_promocode(pid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM promocode_uses WHERE promocode_id=?", (pid,))
        await db.execute("DELETE FROM promocodes WHERE id=?", (pid,)); await db.commit()

async def toggle_promocode(pid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE promocodes SET is_active=CASE is_active WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (pid,)); await db.commit()

async def check_promocode_used(promo_id, uid):
    async with aiosqlite.connect(DB_PATH) as db:
        return (await (await db.execute("SELECT 1 FROM promocode_uses WHERE promocode_id=? AND user_id=?", (promo_id, uid))).fetchone()) is not None

async def use_promocode(promo_id, uid):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT INTO promocode_uses (promocode_id,user_id) VALUES (?,?)", (promo_id, uid))
            await db.execute("UPDATE promocodes SET uses_count=uses_count+1 WHERE id=?", (promo_id,))
            await db.commit(); return True
        except Exception: return False

async def apply_promocode(code, uid):
    p = await get_promocode(code=code)
    if not p: return {"ok": False, "error": "Промокод не найден"}
    if not p["is_active"]: return {"ok": False, "error": "Деактивирован"}
    if p["expires_at"]:
        try:
            if datetime.fromisoformat(p["expires_at"]) < datetime.now(): return {"ok": False, "error": "Истёк"}
        except Exception: pass
    if p["max_uses"] > 0 and p["uses_count"] >= p["max_uses"]: return {"ok": False, "error": "Исчерпан"}
    if await check_promocode_used(p["id"], uid): return {"ok": False, "error": "Уже использован"}
    return {"ok": True, "promo": p, "type": p["type"]}

async def set_active_promo(uid, promo_id, pct):
    await set_setting(f"active_promo_{uid}", f"{promo_id}:{pct}")

async def get_active_promo(uid):
    v = await get_setting(f"active_promo_{uid}")
    if not v: return None
    try:
        p = v.split(":"); return int(p[0]), int(p[1])
    except Exception: return None

async def clear_active_promo(uid):
    await set_setting(f"active_promo_{uid}", "")

async def calculate_price_with_promo(uid, pid, base):
    empty = {"final_price": base, "discount": 0, "promo_code": None, "promo_id": None}
    a = await get_active_promo(uid)
    if not a: return empty
    promo_id, pct = a
    p = await get_promocode(promo_id=promo_id)
    if not p or not p["is_active"]:
        await clear_active_promo(uid); return empty
    if p["expires_at"]:
        try:
            if datetime.fromisoformat(p["expires_at"]) < datetime.now():
                await clear_active_promo(uid); return empty
        except Exception: pass
    if p["max_uses"] > 0 and p["uses_count"] >= p["max_uses"]:
        await clear_active_promo(uid); return empty
    if await check_promocode_used(promo_id, uid):
        await clear_active_promo(uid); return empty
    if p["product_id"] and p["product_id"] != pid: return empty
    if p["category_id"]:
        prod = await get_product(pid)
        if not prod or prod["category_id"] != p["category_id"]: return empty
    if p["min_purchase"] and base < p["min_purchase"]: return empty
    d = round(base * pct / 100, 2)
    return {"final_price": max(round(base - d, 2), 0.01), "discount": d, "promo_code": p["code"], "promo_id": promo_id}

async def sb_list(section=None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if section: rows = await (await db.execute("SELECT * FROM section_buttons WHERE section=? ORDER BY sort_order,id", (section,))).fetchall()
        else: rows = await (await db.execute("SELECT * FROM section_buttons ORDER BY section,sort_order,id")).fetchall()
        return [dict(r) for r in rows]

async def sb_add(section, text, url=None, callback_data=None):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("INSERT INTO section_buttons (section,text,url,callback_data) VALUES (?,?,?,?)", (section, text, url, callback_data))
        await db.commit(); return cur.lastrowid

async def sb_get(bid):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        r = await (await db.execute("SELECT * FROM section_buttons WHERE id=?", (bid,))).fetchone()
        return dict(r) if r else None

async def sb_delete(bid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM section_buttons WHERE id=?", (bid,)); await db.commit()

async def sb_toggle(bid):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE section_buttons SET is_active=CASE is_active WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (bid,)); await db.commit()

async def sb_update(bid, **kw):
    if not kw: return
    f = ", ".join(f"{k}=?" for k in kw)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE section_buttons SET {f} WHERE id=?", list(kw.values())+[bid]); await db.commit()
