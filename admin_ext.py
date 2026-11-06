import asyncio, html, logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import database as db, db_ext as dx, keyboards as kb
from config import ADMIN_IDS
from utils import send_or_edit

log = logging.getLogger(__name__)
router = Router()
router.message.filter(F.from_user.id.in_(set(ADMIN_IDS)))
router.callback_query.filter(F.from_user.id.in_(set(ADMIN_IDS)))

class AX(StatesGroup):
    cat_name = State()
    field = State()
    prod_name = State()
    prod_price = State()
    prod_desc = State()
    setting = State()
    bc_msg = State()

# ---------- helpers ----------
def _ents(msg):
    return msg.entities or msg.caption_entities or []

def first_custom_emoji(msg):
    for e in _ents(msg):
        if e.type == "custom_emoji" and getattr(e, "custom_emoji_id", None):
            return e.custom_emoji_id
    return None

def strip_custom(text, entities):
    if not text:
        return ""
    ce = sorted([e for e in (entities or []) if e.type == "custom_emoji"], key=lambda e: e.offset)
    if not ce:
        return text.strip()
    b = text.encode("utf-16-le")
    out, pos = bytearray(), 0
    for e in ce:
        s = e.offset * 2
        out += b[pos:s]
        pos = s + e.length * 2
    out += b[pos:]
    return out.decode("utf-16-le", errors="ignore").strip()

def html_of(msg):
    try:
        v = msg.html_text
        if v:
            return v
    except Exception:
        pass
    return html.escape(msg.text or msg.caption or "")

async def _menu(event):
    await send_or_edit(event, "⚙️ <b>Админ-панель</b>", reply_markup=kb.admin_menu_kb())

@router.message(Command("cancel"))
async def ax_cancel_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Отменено", reply_markup=kb.admin_menu_kb())

@router.callback_query(F.data == "ax:cancel")
async def ax_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await _menu(call)

# ---------- Категории ----------
async def show_cats(event, parent):
    cats = await dx.get_cats(parent, only_active=False)
    if parent == 0:
        title = "📁 <b>Категории</b>\n\nВыбери категорию или добавь новую."
    else:
        c = await dx.get_cat(parent)
        title = f"📂 <b>Подкатегории</b> → {dx.title_html(c) if c else parent}"
    await send_or_edit(event, title, reply_markup=kb.ax_cats_kb(cats, parent))

async def show_cat_admin(event, cid):
    c = await dx.get_cat(cid)
    if not c:
        await send_or_edit(event, "❌ Категория не найдена", reply_markup=kb.back_only_kb("ax:cats:0"))
        return
    subs = await dx.get_cats(cid, False)
    prods = await dx.get_prods(cid, False)
    parent = int(c.get("parent_id") or 0)
    text = (f"📁 <b>{dx.title_html(c)}</b>\n\n"
            f"🆔 {c['id']} | Родитель: {parent or 'корень'}\n"
            f"✨ Premium-иконка: <code>{c.get('icon_emoji_id') or 'нет'}</code>\n"
            f"📂 Подкатегорий: <b>{len(subs)}</b> | 📦 Товаров: <b>{len(prods)}</b>\n"
            f"📊 {'🟢 видна' if c.get('is_active') else '🔴 скрыта'}\n\n"
            f"📝 {c.get('description') or '—'}")
    await send_or_edit(event, text, reply_markup=kb.ax_cat_kb(c, len(subs), len(prods)), image_id=c.get("image_id") or None)

@router.callback_query(F.data.in_({"adm:cats", "adm:products"}))
async def old_cats(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_cats(call, 0)

@router.callback_query(F.data.startswith("ax:cats:"))
async def ax_cats(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_cats(call, int(call.data.split(":")[2]))

@router.callback_query(F.data.startswith("ax:cat:"))
async def ax_cat(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_cat_admin(call, int(call.data.split(":")[2]))

@router.callback_query(F.data.startswith("ax:cat_add:"))
async def ax_cat_add(call: CallbackQuery, state: FSMContext):
    parent = int(call.data.split(":")[2])
    await state.set_state(AX.cat_name)
    await state.update_data(parent=parent)
    await send_or_edit(call, "➕ <b>Новая " + ("категория" if parent == 0 else "подкатегория") + "</b>\n\n"
                       "Пришли название. Можно с ✨ Premium emoji в начале — он станет иконкой кнопки.",
                       reply_markup=kb.ax_cancel_kb())

@router.message(AX.cat_name)
async def ax_cat_add_save(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Пришли текст")
        return
    d = await state.get_data()
    await state.clear()
    plain = strip_custom(message.text, message.entities) or message.text.strip()
    cid = await dx.add_cat(plain, html_of(message), d.get("parent", 0), first_custom_emoji(message))
    await message.answer("✅ Создано")
    await show_cat_admin(message, cid)

@router.callback_query(F.data.startswith("ax:cat_tog:"))
async def ax_cat_tog(call: CallbackQuery):
    cid = int(call.data.split(":")[2])
    await dx.toggle_row("categories", cid)
    await call.answer("✅")
    await show_cat_admin(call, cid)

@router.callback_query(F.data.startswith("ax:cat_del:"))
async def ax_cat_del(call: CallbackQuery):
    cid = int(call.data.split(":")[2])
    if await dx.get_cats(cid, False) or await dx.get_prods(cid, False):
        await call.answer("❌ Сначала удали подкатегории и товары внутри", show_alert=True)
        return
    await send_or_edit(call, "🗑 Удалить категорию?", reply_markup=kb.ax_confirm_kb(f"ax:cat_del2:{cid}", f"ax:cat:{cid}"))

@router.callback_query(F.data.startswith("ax:cat_del2:"))
async def ax_cat_del2(call: CallbackQuery):
    cid = int(call.data.split(":")[2])
    c = await dx.get_cat(cid)
    parent = int(c.get("parent_id") or 0) if c else 0
    await dx.delete_row("categories", cid)
    await call.answer("🗑 Удалено")
    await show_cats(call, parent)

# ---------- Товары ----------
async def show_prods(event, cid):
    prods = await dx.get_prods(cid, False)
    for p in prods:
        p["stock"] = await db.get_available_items_count(p["id"])
    c = await dx.get_cat(cid)
    await send_or_edit(event, f"📦 <b>Товары</b> → {dx.title_html(c) if c else cid}", reply_markup=kb.ax_prods_kb(prods, cid))

async def show_prod_admin(event, pid):
    p = await dx.get_prod(pid)
    if not p:
        await send_or_edit(event, "❌ Товар не найден", reply_markup=kb.back_only_kb("ax:cats:0"))
        return
    stock = await db.get_available_items_count(pid)
    text = (f"<b>{dx.title_html(p, '📦')}</b>\n\n"
            f"💰 Цена: <b>{p['price']}$</b> | 📊 В наличии: <b>{stock}</b>\n"
            f"✨ Premium-иконка: <code>{p.get('icon_emoji_id') or 'нет'}</code>\n"
            f"📊 {'🟢 виден' if p.get('is_active') else '🔴 скрыт'}\n\n"
            f"📝 {p.get('description') or '—'}")
    await send_or_edit(event, text, reply_markup=kb.ax_prod_kb(p), image_id=p.get("image_id") or None)

@router.callback_query(F.data.startswith("ax:prods:"))
async def ax_prods(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_prods(call, int(call.data.split(":")[2]))

@router.callback_query(F.data.startswith("ax:prod:"))
async def ax_prod(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_prod_admin(call, int(call.data.split(":")[2]))

@router.callback_query(F.data.startswith("ax:prod_add:"))
async def ax_prod_add(call: CallbackQuery, state: FSMContext):
    await state.set_state(AX.prod_name)
    await state.update_data(cid=int(call.data.split(":")[2]))
    await send_or_edit(call, "➕ <b>Новый товар</b>\n\n1/3 Пришли название (можно с ✨ Premium emoji):", reply_markup=kb.ax_cancel_kb())

@router.message(AX.prod_name)
async def ax_prod_name(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Пришли текст")
        return
    plain = strip_custom(message.text, message.entities) or message.text.strip()
    await state.update_data(name=plain, name_html=html_of(message), icon=first_custom_emoji(message))
    await state.set_state(AX.prod_price)
    await message.answer("2/3 Цена в $ (например 4.99):", reply_markup=kb.ax_cancel_kb())

@router.message(AX.prod_price)
async def ax_prod_price(message: Message, state: FSMContext):
    try:
        price = float((message.text or "").replace(",", "."))
        if price <= 0:
            raise ValueError
    except Exception:
        await message.answer("❌ Введи число больше 0")
        return
    await state.update_data(price=price)
    await state.set_state(AX.prod_desc)
    await message.answer("3/3 Описание (можно с Premium emoji и форматированием) или /skip:", reply_markup=kb.ax_cancel_kb())

@router.message(AX.prod_desc)
async def ax_prod_desc(message: Message, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    desc = "" if (message.text or "").strip() == "/skip" else html_of(message)
    pid = await dx.add_prod(d["cid"], d["name"], d["name_html"], d["price"], desc, d.get("icon"))
    await message.answer("✅ Товар создан. Теперь загрузи позиции кнопкой «📤 Загрузить позиции».")
    await show_prod_admin(message, pid)

@router.callback_query(F.data.startswith("ax:prod_tog:"))
async def ax_prod_tog(call: CallbackQuery):
    pid = int(call.data.split(":")[2])
    await dx.toggle_row("products", pid)
    await call.answer("✅")
    await show_prod_admin(call, pid)

@router.callback_query(F.data.startswith("ax:prod_del:"))
async def ax_prod_del(call: CallbackQuery):
    pid = int(call.data.split(":")[2])
    await send_or_edit(call, "🗑 Удалить товар?", reply_markup=kb.ax_confirm_kb(f"ax:prod_del2:{pid}", f"ax:prod:{pid}"))

@router.callback_query(F.data.startswith("ax:prod_del2:"))
async def ax_prod_del2(call: CallbackQuery):
    pid = int(call.data.split(":")[2])
    p = await dx.get_prod(pid)
    await dx.delete_row("products", pid)
    await call.answer("🗑 Удалено")
    await show_prods(call, p["category_id"] if p else 0)

# ---------- Редактирование полей ----------
PROMPTS = {
    "name": "✏️ Пришли новое название (можно с ✨ Premium emoji):",
    "emoji": "😀 Пришли эмодзи.\n✨ Premium emoji станет иконкой на кнопке.\n/delete — убрать иконку.",
    "desc": "📝 Пришли описание (Premium emoji и форматирование сохранятся) или /delete:",
    "image": "🖼 Пришли фото или /delete:",
    "price": "💰 Пришли новую цену в $:",
}

@router.callback_query(F.data.startswith("ax:cf:") | F.data.startswith("ax:pf:"))
async def ax_field(call: CallbackQuery, state: FSMContext):
    _, k, field, rid = call.data.split(":")
    await state.set_state(AX.field)
    await state.update_data(kind="cat" if k == "cf" else "prod", field=field, id=int(rid))
    await send_or_edit(call, PROMPTS.get(field, "Пришли значение:"), reply_markup=kb.ax_cancel_kb())

@router.message(AX.field)
async def ax_field_save(message: Message, state: FSMContext):
    d = await state.get_data()
    kind, field, rid = d["kind"], d["field"], int(d["id"])
    table = "categories" if kind == "cat" else "products"
    txt = (message.text or message.caption or "").strip()
    upd = {}
    if field == "name":
        if not message.text:
            await message.answer("❌ Пришли текст")
            return
        upd = {"name": strip_custom(message.text, message.entities) or message.text.strip(), "name_html": html_of(message)}
        ic = first_custom_emoji(message)
        if ic:
            upd["icon_emoji_id"] = ic
    elif field == "emoji":
        if txt == "/delete":
            upd = {"icon_emoji_id": None}
        else:
            ic = first_custom_emoji(message)
            if kind == "prod" and not ic:
                await message.answer("❌ Для товара пришли именно ✨ Premium emoji или /delete")
                return
            upd = {"icon_emoji_id": ic}
            if kind == "cat":
                upd["emoji"] = (message.text or "📁").strip()[:8]
    elif field == "desc":
        upd = {"description": "" if txt == "/delete" else html_of(message)}
    elif field == "image":
        if txt == "/delete":
            upd = {"image_id": None}
        elif message.photo:
            upd = {"image_id": message.photo[-1].file_id}
        else:
            await message.answer("❌ Пришли фото или /delete")
            return
    elif field == "price":
        try:
            price = float(txt.replace(",", "."))
            if price <= 0:
                raise ValueError
        except Exception:
            await message.answer("❌ Введи число больше 0")
            return
        upd = {"price": price}
    await dx.update_row(table, rid, **upd)
    await state.clear()
    await message.answer("✅ Сохранено")
    if kind == "cat":
        await show_cat_admin(message, rid)
    else:
        await show_prod_admin(message, rid)

# ---------- Тексты (с Premium emoji) ----------
@router.callback_query(F.data.startswith("ax:set:") | F.data.startswith("adm:txt:"))
async def ax_setting(call: CallbackQuery, state: FSMContext):
    key = call.data.split(":", 2)[2]
    await state.set_state(AX.setting)
    await state.update_data(key=key)
    cur = await db.get_setting(key) or ""
    await send_or_edit(call, f"📝 <b>Редактирование:</b> <code>{key}</code>\n\n"
                       f"Пришли новый текст. Поддерживаются ✨ Premium emoji и форматирование.\n"
                       f"/delete — очистить.\n\n<b>Сейчас:</b>\n<code>{html.escape(cur)[:1500] or '—'}</code>",
                       reply_markup=kb.ax_cancel_kb())

@router.message(AX.setting)
async def ax_setting_save(message: Message, state: FSMContext):
    d = await state.get_data()
    key = d.get("key")
    await state.clear()
    if (message.text or "").strip() == "/delete":
        await db.set_setting(key, "")
    elif key.startswith("btn_"):
        await db.set_setting(key, strip_custom(message.text or "", message.entities))
        ic = first_custom_emoji(message)
        if ic:
            await db.set_setting("icon_btn_" + key[4:], ic)
    elif key == "manual_usdt_address":
        await db.set_setting(key, (message.text or "").strip())
    else:
        await db.set_setting(key, html_of(message))
    if key and key.startswith("tpl_"):
        await message.answer("✅ Сохранено")
        await show_tpl_list(message)
    else:
        await message.answer("✅ Сохранено", reply_markup=kb.admin_menu_kb())

# ---------- Отображение ----------
async def show_layout(event):
    cur = {k: await dx.get_cols(k, 2 if k == "cols_main" else 1) for k in ("cols_main", "cols_cats", "cols_prods")}
    await send_or_edit(event, "🎛 <b>Отображение кнопок</b>\n\nВыбери количество колонок для каждого раздела:", reply_markup=kb.ax_layout_kb(cur))

@router.callback_query(F.data == "ax:layout")
async def ax_layout(call: CallbackQuery):
    await show_layout(call)

@router.callback_query(F.data.startswith("ax:cols:"))
async def ax_cols(call: CallbackQuery):
    _, _, key, n = call.data.split(":")
    await db.set_setting(key, n)
    await call.answer(f"✅ {n} колонки")
    await show_layout(call)

# ---------- Уведомления ----------
async def _on(key):
    return ((await db.get_setting(key)) or "1") != "0"

async def show_notify(event):
    await send_or_edit(event, "🔔 <b>Уведомления администраторам</b>\n\nПриходят прямо в этот бот всем ID из ADMIN_IDS.",
                       reply_markup=kb.ax_notify_kb(await _on("notify_new_users"), await _on("notify_sales")))

@router.callback_query(F.data == "ax:notify")
async def ax_notify(call: CallbackQuery):
    await show_notify(call)

@router.callback_query(F.data.startswith("ax:ntog:"))
async def ax_ntog(call: CallbackQuery):
    key = call.data.split(":")[2]
    await db.set_setting(key, "0" if await _on(key) else "1")
    await call.answer("✅")
    await show_notify(call)

# ---------- Рассылка ----------
@router.callback_query(F.data.in_({"ax:bc", "adm:broadcast"}))
async def ax_bc(call: CallbackQuery, state: FSMContext):
    await state.set_state(AX.bc_msg)
    await send_or_edit(call, "📣 <b>Рассылка</b>\n\nПришли сообщение для рассылки: текст, фото, видео, GIF.\n"
                       "✨ Premium emoji и форматирование сохранятся.", reply_markup=kb.ax_cancel_kb())

@router.message(AX.bc_msg)
async def ax_bc_msg(message: Message, state: FSMContext):
    await state.set_state(None)
    await state.update_data(bc_chat=message.chat.id, bc_mid=message.message_id)
    n = len(await dx.all_user_ids())
    try:
        await message.bot.copy_message(message.chat.id, message.chat.id, message.message_id)
    except Exception as e:
        await message.answer(f"⚠️ Предпросмотр не удался: <code>{html.escape(str(e))[:150]}</code>")
    await message.answer(f"👆 Предпросмотр.\nОтправить <b>{n}</b> пользователям?", reply_markup=kb.ax_bc_confirm_kb())

async def _run_bc(bot, admin_id, chat_id, mid):
    ok = fail = 0
    for uid in await dx.all_user_ids():
        for attempt in range(2):
            try:
                await bot.copy_message(uid, chat_id, mid)
                ok += 1
                break
            except Exception as e:
                ra = getattr(e, "retry_after", None)
                if ra and attempt == 0:
                    await asyncio.sleep(float(ra) + 1)
                    continue
                fail += 1
                break
        await asyncio.sleep(0.05)
    try:
        await bot.send_message(admin_id, f"📣 <b>Рассылка завершена</b>\n\n✅ Доставлено: {ok}\n❌ Ошибок: {fail}")
    except Exception:
        pass

@router.callback_query(F.data == "ax:bc_go")
async def ax_bc_go(call: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    if not d.get("bc_mid"):
        await call.answer("❌ Нет сообщения для рассылки", show_alert=True)
        return
    await call.answer("🚀 Рассылка запущена")
    await send_or_edit(call, "🚀 Рассылка запущена. По окончании придёт отчёт.", reply_markup=kb.back_only_kb("admin_panel"))
    asyncio.create_task(_run_bc(call.bot, call.from_user.id, d["bc_chat"], d["bc_mid"]))

# TEXTS_ADMIN_V29
from texts import INFO as TPL_INFO, DEFAULTS as TPL_DEF

async def show_tpl_list(event):
    await send_or_edit(event, "✏️ <b>Тексты разделов</b>\n\nВыбери раздел. В текстах можно использовать ✨ Premium emoji, "
                       "форматирование и переменные в фигурных скобках — они подставятся автоматически.",
                       reply_markup=kb.ax_tpls_kb())

@router.callback_query(F.data == "ax:tpls")
async def ax_tpls(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_tpl_list(call)

@router.callback_query(F.data.startswith("ax:tpl:"))
async def ax_tpl(call: CallbackQuery, state: FSMContext):
    key = call.data.split(":", 2)[2]
    if key not in TPL_INFO:
        await call.answer("Не найдено", show_alert=True)
        return
    title, ph = TPL_INFO[key]
    cur = ((await db.get_setting(key)) or "").strip() or TPL_DEF[key]
    vars_txt = "\n".join(f"<code>{{{k}}}</code> — {v}" for k, v in ph.items())
    await state.set_state(AX.setting)
    await state.update_data(key=key)
    text = (f"✏️ <b>{title}</b>\n\n<b>Переменные:</b>\n{vars_txt}\n\n"
            f"Пришли новый текст. ✨ Premium emoji и форматирование сохранятся.\n"
            f"/delete — вернуть стандартный.\n\n<b>Сейчас:</b>\n\n{cur}")
    try:
        await send_or_edit(call, text, reply_markup=kb.cancel_kb("ax:tpls"))
    except Exception:
        await send_or_edit(call, f"✏️ <b>{title}</b>\n\n<b>Переменные:</b>\n{vars_txt}\n\nПришли новый текст или /delete.",
                           reply_markup=kb.cancel_kb("ax:tpls"))

async def _show_btn(event, name):
    names = dict(kb.CUSTOM_BUTTONS)
    key = kb.BTN_TEXT_KEYS.get(name, "btn_" + name)
    text = await db.get_setting(key)
    icon = await db.get_setting("icon_btn_" + name)
    style = await db.get_setting("style_btn_" + name) or "обычный"
    await send_or_edit(event, f"🎛 <b>{names.get(name, name)}</b>\n\n📝 Текст: {html.escape(text or 'по умолчанию')}\n"
                       f"✨ Premium icon ID: <code>{icon or 'нет'}</code>\n🎨 Цвет: <b>{style}</b>",
                       reply_markup=kb.admin_button_detail_kb(name))

@router.callback_query(F.data.startswith("adm:btn:"))
async def ax_btn_detail(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await _show_btn(call, call.data.split(":")[2])

@router.callback_query(F.data.startswith("adm:setstyle:"))
async def ax_btn_setstyle(call: CallbackQuery):
    _, _, name, style = call.data.split(":")
    await db.set_setting("style_btn_" + name, "" if style == "default" else style)
    await call.answer("✅ Цвет сохранён")
    await _show_btn(call, name)
