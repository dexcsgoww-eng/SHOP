import html
import aiosqlite
import database as db
from database import DB_PATH

async def _cols(conn, table):
    rows = await (await conn.execute(f"PRAGMA table_info({table})")).fetchall()
    return [r[1] for r in rows]

async def ensure_schema():
    async with aiosqlite.connect(DB_PATH) as c:
        spec = {
            "categories": [("parent_id", "INTEGER DEFAULT 0"), ("icon_emoji_id", "TEXT"), ("name_html", "TEXT")],
            "products": [("icon_emoji_id", "TEXT"), ("name_html", "TEXT")],
        }
        for table, adds in spec.items():
            cols = await _cols(c, table)
            if not cols:
                continue
            for n, t in adds:
                if n not in cols:
                    await c.execute(f"ALTER TABLE {table} ADD COLUMN {n} {t}")
        await c.commit()

async def _fetch(sql, args=()):
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await c.execute(sql, args)).fetchall()]

async def _one(sql, args=()):
    r = await _fetch(sql, args)
    return r[0] if r else None

async def get_cats(parent=0, only_active=True):
    sql = "SELECT * FROM categories WHERE COALESCE(parent_id,0)=?"
    if only_active:
        sql += " AND is_active=1"
    return await _fetch(sql + " ORDER BY id", (int(parent),))

async def get_cat(cid):
    return await _one("SELECT * FROM categories WHERE id=?", (int(cid),))

async def get_prods(cid, only_active=True):
    sql = "SELECT * FROM products WHERE category_id=?"
    if only_active:
        sql += " AND is_active=1"
    return await _fetch(sql + " ORDER BY id", (int(cid),))

async def get_prod(pid):
    return await _one("SELECT * FROM products WHERE id=?", (int(pid),))

async def _insert(table, data):
    async with aiosqlite.connect(DB_PATH) as c:
        cols = await _cols(c, table)
        data = {k: v for k, v in data.items() if k in cols}
        keys = ", ".join(data.keys())
        q = ", ".join("?" for _ in data)
        cur = await c.execute(f"INSERT INTO {table} ({keys}) VALUES ({q})", tuple(data.values()))
        await c.commit()
        return cur.lastrowid

async def add_cat(name, name_html, parent=0, icon=None, emoji="📁"):
    return await _insert("categories", {"name": name, "name_html": name_html, "parent_id": int(parent),
                                        "icon_emoji_id": icon, "emoji": emoji, "description": "", "is_active": 1})

async def add_prod(cid, name, name_html, price, description="", icon=None):
    return await _insert("products", {"category_id": int(cid), "name": name, "name_html": name_html,
                                      "price": float(price), "description": description,
                                      "icon_emoji_id": icon, "is_active": 1})

async def update_row(table, rid, **fields):
    async with aiosqlite.connect(DB_PATH) as c:
        cols = await _cols(c, table)
        fields = {k: v for k, v in fields.items() if k in cols}
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        await c.execute(f"UPDATE {table} SET {sets} WHERE id=?", (*fields.values(), int(rid)))
        await c.commit()

async def toggle_row(table, rid):
    async with aiosqlite.connect(DB_PATH) as c:
        await c.execute(f"UPDATE {table} SET is_active = CASE is_active WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (int(rid),))
        await c.commit()

async def delete_row(table, rid):
    async with aiosqlite.connect(DB_PATH) as c:
        await c.execute(f"DELETE FROM {table} WHERE id=?", (int(rid),))
        await c.commit()

async def all_user_ids():
    async with aiosqlite.connect(DB_PATH) as c:
        cols = await _cols(c, "users")
        sql = "SELECT user_id FROM users"
        if "is_banned" in cols:
            sql += " WHERE COALESCE(is_banned,0)=0"
        return [r[0] for r in await (await c.execute(sql)).fetchall()]

async def count_users():
    r = await _one("SELECT COUNT(*) AS n FROM users")
    return r["n"] if r else 0

async def get_cols(key, default=1):
    try:
        v = int((await db.get_setting(key)) or default)
        return max(1, min(3, v))
    except Exception:
        return default

async def cat_stock(cid, depth=0):
    total = 0
    for p in await get_prods(cid):
        total += await db.get_available_items_count(p["id"])
    if depth < 6:
        for sc in await get_cats(cid):
            total += await cat_stock(sc["id"], depth + 1)
    return total

def title_html(row, default_emoji="📁"):
    name_html = row.get("name_html") or html.escape(str(row.get("name") or ""))
    if "tg-emoji" in name_html:
        return name_html
    icon = row.get("icon_emoji_id")
    em = row.get("emoji") or default_emoji
    if icon:
        return f'<tg-emoji emoji-id="{icon}">{em}</tg-emoji> {name_html}'
    return f"{em} {name_html}"

# ===== SECTION_BUTTONS_V1 (update_v30) =====
SB_SECTIONS = {
    "welcome": "🏠 Главное меню",
    "faq": "ℹ️ FAQ / Информация",
    "support": "💬 Поддержка",
    "profile": "👤 Профиль",
    "referral": "👥 Рефералка",
}


async def _ensure_sb_table():
    async with aiosqlite.connect(DB_PATH) as c:
        await c.execute(
            "CREATE TABLE IF NOT EXISTS section_buttons ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "section TEXT NOT NULL, text TEXT NOT NULL, "
            "url TEXT, callback_data TEXT, "
            "sort_order INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1)"
        )
        await c.commit()


async def sb_list(section):
    await _ensure_sb_table()
    return await _fetch(
        "SELECT * FROM section_buttons WHERE section=? ORDER BY sort_order, id",
        (section,),
    )


async def sb_add(section, text, url=None, callback_data=None):
    await _ensure_sb_table()
    async with aiosqlite.connect(DB_PATH) as c:
        row = await (await c.execute(
            "SELECT COALESCE(MAX(sort_order),0)+1 FROM section_buttons WHERE section=?",
            (section,))).fetchone()
        cur = await c.execute(
            "INSERT INTO section_buttons (section, text, url, callback_data, sort_order) "
            "VALUES (?,?,?,?,?)",
            (section, text, url, callback_data, row[0]))
        await c.commit()
        return cur.lastrowid


async def sb_delete(bid):
    await _ensure_sb_table()
    async with aiosqlite.connect(DB_PATH) as c:
        await c.execute("DELETE FROM section_buttons WHERE id=?", (int(bid),))
        await c.commit()


async def sb_toggle(bid):
    await _ensure_sb_table()
    async with aiosqlite.connect(DB_PATH) as c:
        await c.execute(
            "UPDATE section_buttons SET is_active = CASE is_active WHEN 1 THEN 0 ELSE 1 END "
            "WHERE id=?", (int(bid),))
        await c.commit()

