import re, logging
from typing import Optional
import database as db
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)

BTN_TEXT_KEYS = {
    "catalog": "btn_catalog", "profile": "btn_profile", "referral": "btn_referral",
    "faq": "btn_faq", "support": "btn_support", "buy": "btn_buy",
    "pay_balance": "btn_pay_balance", "pay_manual": "btn_pay_manual",
}
CUSTOM_BUTTONS = [
    ("catalog", "🛍 Каталог"), ("profile", "👤 Профиль"), ("referral", "👥 Рефералка"),
    ("faq", "ℹ️ FAQ"), ("support", "💬 Поддержка"), ("buy", "🛒 Купить"),
    ("pay_balance", "💰 С баланса"), ("pay_manual", "💎 USDT TRC20"),
]

def _ensure_button_fields():
    try:
        fields = InlineKeyboardButton.model_fields
        if "style" not in fields or "icon_custom_emoji_id" not in fields:
            from pydantic.fields import FieldInfo
            for n in ("style", "icon_custom_emoji_id"):
                if n not in fields:
                    fields[n] = FieldInfo(default=None, annotation=Optional[str])
                    InlineKeyboardButton.__annotations__[n] = Optional[str]
            InlineKeyboardButton.model_rebuild(force=True)
            try:
                InlineKeyboardMarkup.model_rebuild(force=True)
            except Exception:
                pass
        b = InlineKeyboardButton(text="t", callback_data="t", style="primary", icon_custom_emoji_id="5005")
        d = b.model_dump(exclude_none=True)
        return d.get("style") == "primary" and d.get("icon_custom_emoji_id") == "5005"
    except Exception as e:
        logger.warning(f"[buttons] {e}")
        return False

_HAS_STYLE_ICON = _ensure_button_fields()

def _clean(v):
    return re.sub(r"<[^>]+>", "", str(v or "")).strip()

def B(t, d=None, u=None, style=None, icon=None):
    kw = {"text": t}
    if u:
        kw["url"] = u
    else:
        kw["callback_data"] = d
    if style in ("primary", "success", "danger"):
        kw["style"] = style
    if icon and str(icon).strip().isdigit():
        kw["icon_custom_emoji_id"] = str(icon).strip()
    try:
        return InlineKeyboardButton(**kw)
    except Exception:
        kw.pop("style", None)
        kw.pop("icon_custom_emoji_id", None)
        return InlineKeyboardButton(**kw)

def M(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)

def grid(btns, cols):
    try:
        cols = int(cols)
    except Exception:
        cols = 1
    cols = max(1, min(3, cols))
    return [btns[i:i + cols] for i in range(0, len(btns), cols)]

async def CB(name, fallback, d=None, u=None, default_style=None):
    text = _clean(await db.get_setting(BTN_TEXT_KEYS.get(name, "btn_" + name))) or fallback
    icon = await db.get_setting("icon_btn_" + name)
    style = await db.get_setting("style_btn_" + name)
    if style not in ("primary", "success", "danger"):
        style = default_style
    return B(text, d, u, style=style, icon=icon)

async def main_menu_kb():
    try:
        cols = int((await db.get_setting("cols_main")) or 2)
    except Exception:
        cols = 2
    cat = await CB("catalog", "🛍 Каталог", "catalog", default_style="primary")
    others = [
        await CB("profile", "👤 Профиль", "profile"),
        await CB("referral", "👥 Рефералка", "referral"),
        await CB("faq", "ℹ️ FAQ", "faq"),
        await CB("support", "💬 Поддержка", "support"),
    ]
    return M([[cat]] + grid(others, cols))

# ---------- Каталог (пользователь) ----------
def cat_button(c):
    icon = c.get("icon_emoji_id")
    name = _clean(c.get("name"))
    em = _clean(c.get("emoji")) or "📁"
    text = name if icon else f"{em} {name}"
    if c.get("stock") is not None:
        text += f" ({c['stock']})"
    return B(text, f"cat:{c['id']}", icon=icon)

def prod_button(p):
    icon = p.get("icon_emoji_id")
    name = _clean(p.get("name"))
    text = (name if icon else f"📦 {name}") + f" — {p['price']}$"
    if p.get("stock") is not None:
        text += f" ({p['stock']})"
    return B(text, f"product:{p['id']}", icon=icon)

def catalog_kb(cats, cols):
    rows = grid([cat_button(c) for c in cats], cols)
    rows.append([B("◀️ Назад", "main_menu", style="danger")])
    return M(rows)

def category_kb(subcats, prods, cols_c, cols_p, back):
    rows = grid([cat_button(c) for c in subcats], cols_c) + grid([prod_button(p) for p in prods], cols_p)
    rows.append([B("◀️ Назад", back, style="danger")])
    return M(rows)

def categories_kb(cats):
    return catalog_kb(cats, 1)

def products_kb(prods, cat_id):
    return category_kb([], prods, 1, 1, "catalog")

async def product_detail_kb(pid, cat_id):
    return M([[await CB("buy", "🛒 Купить", f"buy:{pid}", default_style="success")], [B("◀️ Назад", f"cat:{cat_id}", style="danger")]])

async def payment_method_kb(pid):
    return M([
        [await CB("pay_crypto", "🤖 CryptoBot", f"pay:crypto_bot:{pid}", default_style="primary")],
        [await CB("pay_balance", "💰 С баланса", f"pay:balance:{pid}", default_style="success")],
        [await CB("pay_manual", "💎 USDT TRC20", f"pay:manual:{pid}", default_style="success")],
        [B("◀️ Назад", f"product:{pid}", style="danger")],
    ])

def check_payment_kb(method, inv_id, pay_url, pid):
    return M([[B("💳 Оплатить", u=pay_url, style="primary")], [B("🔄 Проверить", f"check:{method}:{inv_id}:{pid}", style="success")], [B("❌ Отмена", f"product:{pid}", style="danger")]])

def balance_confirm_kb(pid):
    return M([[B("✅ Подтвердить", f"confirm_balance:{pid}", style="success")], [B("❌ Отмена", f"product:{pid}", style="danger")]])

async def topup_method_kb():
    return M([
        [await CB("pay_crypto", "🤖 CryptoBot", "topup_method:crypto_bot", default_style="primary")],
        [await CB("pay_manual", "💎 USDT TRC20 вручную", "topup_method:manual", default_style="success")],
        [B("◀️ Назад", "profile", style="danger")],
    ])

def topup_amount_kb(method):
    return M([[B("💵 5$", f"topup_amt:{method}:5"), B("💵 10$", f"topup_amt:{method}:10")], [B("💵 25$", f"topup_amt:{method}:25"), B("💵 50$", f"topup_amt:{method}:50")], [B("💵 100$", f"topup_amt:{method}:100")], [B("✏️ Своя сумма", f"topup_amt:{method}:custom")], [B("◀️ Назад", "topup_menu", style="danger")]])

def topup_kb():
    return topup_amount_kb("crypto_bot")

def topup_check_kb(method, inv_id, pay_url):
    return M([[B("💳 Оплатить", u=pay_url, style="primary")], [B("🔄 Проверить", f"topup_check:{method}:{inv_id}", style="success")], [B("❌ Отмена", "profile", style="danger")]])

def manual_cancel_kb():
    return M([[B("❌ Отменить заявку", "manual_cancel", style="danger")]])

def profile_kb():
    return M([[B("💰 Пополнить баланс", "topup_menu", style="success")], [B("🎁 Промокод", "promo_use", style="primary")], [B("📋 Мои покупки", "my_orders")], [B("👥 Рефералка", "referral")], [B("◀️ Назад", "main_menu", style="danger")]])

def referral_kb():
    return M([[B("💸 Вывести", "withdraw_start", style="success")], [B("◀️ Назад", "main_menu", style="danger")]])

def withdraw_method_kb():
    return M([[B("🤖 CryptoBot", "wd_method:crypto_bot", style="primary")], [B("❌ Отмена", "referral", style="danger")]])

# ---------- Админ ----------
def admin_menu_kb():
    return M([
        [B("📊 Статистика", "adm:stats")],
        [B("🔗 Кнопки разделов", "adm:sbtns", style="primary"), B("🎁 Промокоды", "adm:promos", style="success")],
        [B("📁 Каталог", "ax:cats:0", style="primary"), B("🎛 Отображение", "ax:layout")],
        [B("✏️ Тексты разделов", "ax:tpls", style="success")],
        [B("📝 Текст каталога", "ax:set:catalog_text"), B("🏷 Карточка товара", "ax:card", style="primary")],
        [B("🔔 Уведомления", "ax:notify"), B("🎨 Оформление", "adm:design")],
        [B("💳 Ручные пополнения", "adm:topups", style="primary"), B("💸 Выводы", "adm:withdraws")],
        [B("📢 Обяз. подписка", "adm:subs", style="success")],
        [B("👥 Юзеры", "adm:users"), B("📣 Рассылка", "ax:bc", style="success")],
    ])

def ax_cancel_kb():
    return M([[B("❌ Отмена", "ax:cancel", style="danger")]])

def ax_cats_kb(cats, parent):
    rows = []
    for c in cats:
        mark = "✅" if c.get("is_active") else "❌"
        icon = c.get("icon_emoji_id")
        em = "" if icon else (_clean(c.get("emoji")) or "📁") + " "
        rows.append([B(f"{mark} {em}{_clean(c.get('name'))}", f"ax:cat:{c['id']}", icon=icon)])
    rows.append([B("➕ Добавить " + ("категорию" if parent == 0 else "подкатегорию"), f"ax:cat_add:{parent}", style="success")])
    rows.append([B("◀️ Назад", "admin_panel" if parent == 0 else f"ax:cat:{parent}", style="danger")])
    return M(rows)

def ax_cat_kb(c, n_sub, n_prod):
    cid = c["id"]
    parent = int(c.get("parent_id") or 0)
    return M([
        [B("✏️ Название", f"ax:cf:name:{cid}"), B("😀 Эмодзи/иконка", f"ax:cf:emoji:{cid}")],
        [B("📝 Описание", f"ax:cf:desc:{cid}"), B("🖼 Фото", f"ax:cf:image:{cid}")],
        [B(f"📂 Подкатегории ({n_sub})", f"ax:cats:{cid}", style="primary"), B(f"📦 Товары ({n_prod})", f"ax:prods:{cid}", style="primary")],
        [B("🔴 Скрыть" if c.get("is_active") else "🟢 Показать", f"ax:cat_tog:{cid}")],
        [B("🗑 Удалить", f"ax:cat_del:{cid}", style="danger")],
        [B("◀️ Назад", f"ax:cats:{parent}")],
    ])

def ax_prods_kb(prods, cid):
    rows = []
    for p in prods:
        mark = "✅" if p.get("is_active") else "❌"
        rows.append([B(f"{mark} {_clean(p.get('name'))} — {p['price']}$ ({p.get('stock', 0)})", f"ax:prod:{p['id']}", icon=p.get("icon_emoji_id"))])
    rows.append([B("➕ Добавить товар", f"ax:prod_add:{cid}", style="success")])
    rows.append([B("◀️ Назад", f"ax:cat:{cid}", style="danger")])
    return M(rows)

def ax_prod_kb(p):
    pid = p["id"]
    return M([
        [B("✏️ Название", f"ax:pf:name:{pid}"), B("💰 Цена", f"ax:pf:price:{pid}")],
        [B("📝 Описание", f"ax:pf:desc:{pid}"), B("🖼 Фото", f"ax:pf:image:{pid}")],
        [B("✨ Premium-иконка", f"ax:pf:emoji:{pid}")],
        [B("📤 Загрузить позиции", f"adm:upload:{pid}", style="primary")],
        [B("🔴 Скрыть" if p.get("is_active") else "🟢 Показать", f"ax:prod_tog:{pid}")],
        [B("🗑 Удалить", f"ax:prod_del:{pid}", style="danger")],
        [B("◀️ Назад", f"ax:prods:{p['category_id']}")],
    ])

def ax_confirm_kb(yes, no):
    return M([[B("✅ Да, удалить", yes, style="danger"), B("❌ Нет", no)]])

def ax_layout_kb(cur):
    rows = []
    for key, label in (("cols_main", "🏠 Главное меню"), ("cols_cats", "📁 Категории"), ("cols_prods", "📦 Товары")):
        rows.append([B(label, "noop")])
        rows.append([B(("✅ " if cur.get(key) == n else "") + f"{n} кол.", f"ax:cols:{key}:{n}", style="primary" if cur.get(key) == n else None) for n in (1, 2, 3)])
    rows.append([B("◀️ Назад", "admin_panel", style="danger")])
    return M(rows)

def ax_notify_kb(new_on, sale_on):
    return M([
        [B(("🟢" if new_on else "🔴") + " Новые пользователи", "ax:ntog:notify_new_users", style="success" if new_on else "danger")],
        [B(("🟢" if sale_on else "🔴") + " Покупки", "ax:ntog:notify_sales", style="success" if sale_on else "danger")],
        [B("◀️ Назад", "admin_panel", style="danger")],
    ])

def ax_bc_confirm_kb():
    return M([[B("✅ Отправить всем", "ax:bc_go", style="success"), B("❌ Отмена", "ax:cancel", style="danger")]])

# ---------- Старые админ-клавиатуры (совместимость) ----------
def admin_cats_kb(cats):
    return ax_cats_kb(cats, 0)

def admin_cat_detail_kb(cid, active):
    return M([[B("Открыть", f"ax:cat:{cid}")], [B("◀️ Назад", "ax:cats:0")]])

def admin_products_select_cat_kb(cats):
    return ax_cats_kb(cats, 0)

def admin_prods_in_cat_kb(prods, cat_id):
    return ax_prods_kb(prods, cat_id)

def admin_prod_detail_kb(pid, cat_id, active):
    return M([[B("Открыть товар", f"ax:prod:{pid}")], [B("◀️ Назад", f"ax:prods:{cat_id}")]])

def admin_design_kb():
    return M([[B("📝 Приветствие", "adm:txt:welcome_text")], [B("🖼 Фото приветствия", "adm:img:welcome_image")], [B("📝 FAQ", "adm:txt:faq_text")], [B("🖼 Фото FAQ", "adm:img:faq_image")], [B("📝 Поддержка", "adm:txt:support_text")], [B("🖼 Фото профиля", "adm:img:profile_image")], [B("🖼 Фото каталога", "adm:img:catalog_image")], [B("💎 USDT TRC20 адрес", "adm:txt:manual_usdt_address", style="primary")], [B("📝 Инструкция USDT", "adm:txt:manual_instructions")], [B("🎛 Кнопки: цвет и Premium emoji", "adm:buttons", style="success")], [B("◀️ Назад", "admin_panel", style="danger")]])

def admin_buttons_kb():
    rows = [[B(label, f"adm:btn:{name}")] for name, label in CUSTOM_BUTTONS]
    rows.append([B("◀️ Назад", "adm:design", style="danger")])
    return M(rows)

def admin_button_detail_kb(name):
    key = BTN_TEXT_KEYS.get(name, "btn_catalog")
    return M([[B("📝 Текст кнопки", f"adm:txt:{key}")], [B("✨ Premium emoji (icon)", f"adm:btnicon:{name}", style="primary")], [B("🎨 Цвет кнопки", f"adm:btnstyle:{name}", style="success")], [B("◀️ Назад", "adm:buttons", style="danger")]])

def admin_button_style_kb(name):
    return M([[B("🔵 Синяя (primary)", f"adm:setstyle:{name}:primary", style="primary")], [B("🟢 Зелёная (success)", f"adm:setstyle:{name}:success", style="success")], [B("🔴 Красная (danger)", f"adm:setstyle:{name}:danger", style="danger")], [B("⚪ Обычная", f"adm:setstyle:{name}:default")], [B("◀️ Назад", f"adm:btn:{name}", style="danger")]])

def admin_users_kb():
    return M([[B("🔍 Найти по ID", "adm:find_user")], [B("◀️ Назад", "admin_panel", style="danger")]])

def admin_user_detail_kb(uid, banned):
    return M([[B("✅ Разбанить" if banned else "🚫 Забанить", f"adm:u_ban:{uid}", style="danger")], [B("💰 Начислить баланс", f"adm:u_add:{uid}", style="success"), B("➖ Списать баланс", f"adm:u_sub:{uid}", style="danger")], [B("◀️ Назад", "adm:users")]])

def admin_withdraws_kb(wds):
    rows = [[B(f"#{w['id']} - {w['amount']}$", f"adm:w:{w['id']}")] for w in wds]
    rows.append([B("◀️ Назад", "admin_panel", style="danger")])
    return M(rows)

def admin_withdraw_detail_kb(wid):
    return M([[B("✅ Выплатить", f"adm:w_ok:{wid}", style="success"), B("❌ Отклонить", f"adm:w_no:{wid}", style="danger")], [B("◀️ Назад", "adm:withdraws")]])

def admin_manual_topups_kb(items):
    rows = [[B(f"#{w['id']} - {w['amount']}$ | ID {w['user_id']}", f"adm:top:{w['id']}")] for w in items]
    rows.append([B("◀️ Назад", "admin_panel", style="danger")])
    return M(rows)

def admin_manual_topup_detail_kb(mid):
    return M([[B("✅ Одобрить", f"adm:top_ok:{mid}", style="success"), B("❌ Отклонить", f"adm:top_no:{mid}", style="danger")], [B("◀️ Назад", "adm:topups")]])

def broadcast_confirm_kb():
    return ax_bc_confirm_kb()

def confirm_kb(action, item_id, back="admin_panel"):
    return M([[B("✅ Да", f"cfm:{action}:{item_id}", style="success"), B("❌ Нет", back, style="danger")]])

def cancel_kb(back="admin_panel"):
    return M([[B("❌ Отмена", back, style="danger")]])

def back_only_kb(back="main_menu"):
    return M([[B("◀️ Назад", back, style="danger")]])

def admin_subs_kb(channels, enabled):
    rows = [[B(("🟢 Вкл" if enabled else "🔴 Выкл") + " · переключить", "adm:sub_toggle", style=("success" if enabled else "danger"))]]
    for ch in channels:
        mark = "✅" if ch.get("is_active") else "❌"
        rows.append([B(f"{mark} {ch.get('title') or ch.get('username') or ch.get('chat_id')}", f"adm:sub:{ch['id']}")])
    rows.append([B("➕ Добавить канал", "adm:sub_add", style="success")])
    rows.append([B("◀️ Назад", "admin_panel", style="danger")])
    return M(rows)

def admin_sub_detail_kb(cid, active):
    return M([[B("🔴 Скрыть" if active else "🟢 Показать", f"adm:sub_tog:{cid}")], [B("🔗 Обновить invite-ссылку", f"adm:sub_link:{cid}", style="primary")], [B("🗑 Удалить", f"adm:sub_del:{cid}", style="danger")], [B("◀️ Назад", "adm:subs")]])

def sub_required_kb(channels):
    rows = []
    for ch in channels:
        url = ch.get("invite_link") or (f"https://t.me/{ch['username'].lstrip('@')}" if ch.get("username") else None)
        if url:
            rows.append([B(f"📢 {ch.get('title') or ch.get('username') or 'Канал'}", u=url, style="primary")])
    rows.append([B("✅ Я подписался — проверить", "subs_check", style="success")])
    return M(rows)

# PROFILE_KB_V29
from urllib.parse import quote as _quote
BTN_TEXT_KEYS.update({"topup": "btn_topup", "my_orders": "btn_my_orders", "ref_profile": "btn_ref_profile",
                      "ref_share": "btn_ref_share", "withdraw": "btn_withdraw"})
for _n, _l in (("topup", "💰 Пополнить баланс"), ("my_orders", "📋 Мои покупки"), ("ref_profile", "👥 Рефералка (профиль)"),
               ("ref_share", "📤 Поделиться ссылкой"), ("withdraw", "💸 Вывести")):
    if _n not in dict(CUSTOM_BUTTONS):
        CUSTOM_BUTTONS.append((_n, _l))

async def profile_kb2():
    return M([
        [await CB("topup", "💰 Пополнить баланс", "topup_menu", default_style="success")],
        [await CB("my_orders", "📋 Мои покупки", "my_orders"), await CB("ref_profile", "👥 Рефералка", "ref_profile")],
        [B("◀️ Назад", "main_menu", style="danger")],
    ])

async def referral_kb2(back="main_menu", link=None):
    rows = []
    if link:
        rows.append([await CB("ref_share", "📤 Поделиться ссылкой", u="https://t.me/share/url?url=" + _quote(link, safe=""), default_style="primary")])
    rows.append([await CB("withdraw", "💸 Вывести", "withdraw_start", default_style="success")])
    rows.append([B("◀️ Назад", back, style="danger")])
    return M(rows)

def ax_tpls_kb():
    from texts import INFO
    rows = [[B(title, f"ax:tpl:{key}")] for key, (title, _) in INFO.items()]
    rows.append([B("🎛 Кнопки (текст / цвет / Premium)", "adm:buttons", style="primary")])
    rows.append([B("◀️ Назад", "admin_panel", style="danger")])
    return M(rows)

# ===== SECTION_BUTTONS_V1 (update_v30) =====
import db_ext as _db_ext


async def with_section_buttons(base_kb, section):
    # Добавляет кастомные кнопки раздела (админка -> Кнопки разделов)
    try:
        btns = [b for b in await _db_ext.sb_list(section) if b.get("is_active")]
    except Exception:
        btns = []
    if not btns:
        return base_kb
    rows = list(base_kb.inline_keyboard) if base_kb else []
    custom = []
    for b in btns:
        t = _clean(b.get("text")) or "Кнопка"
        if b.get("url"):
            custom.append(B(t, u=b["url"]))
        elif b.get("callback_data"):
            custom.append(B(t, b["callback_data"]))
    if not custom:
        return base_kb
    if rows and len(rows[-1]) == 1 and "Назад" in rows[-1][0].text:
        rows = rows[:-1] + [[c] for c in custom] + [rows[-1]]
    else:
        rows = rows + [[c] for c in custom]
    return M(rows)
