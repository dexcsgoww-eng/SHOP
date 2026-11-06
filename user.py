import html
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, CommandObject
import database as db, db_ext as dx, keyboards as kb
from config import ADMIN_IDS, REFERRAL_PERCENT, MIN_WITHDRAW
from texts import T, money, ref_link
from utils import send_or_edit
router = Router()

LABEL_DEFAULTS = {"label_price": "💰 Цена:", "label_stock": "📊 В наличии:", "label_unit": "шт"}

async def get_label(key):
    v = ((await db.get_setting(key)) or "").strip()
    return v or LABEL_DEFAULTS.get(key, "")

async def _notify_new_user(message, user):
    if ((await db.get_setting("notify_new_users")) or "1") == "0":
        return
    u = message.from_user
    try:
        total = await dx.count_users()
    except Exception:
        total = "?"
    text = (f"🆕 <b>Новый пользователь</b>\n\n👤 {html.escape(u.full_name or '')}\n"
            f"🔗 {'@' + u.username if u.username else '—'}\n🆔 <code>{u.id}</code>\n"
            f"👥 Реферер: <code>{user.get('referrer_id') or '—'}</code>\n📊 Всего пользователей: <b>{total}</b>")
    for aid in ADMIN_IDS:
        try:
            await message.bot.send_message(aid, text)
        except Exception:
            pass

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    ref = int(command.args) if command.args and command.args.isdigit() else None
    if ref == message.from_user.id:
        ref = None
    user, is_new = await db.get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name, referrer_id=ref)
    if user.get("is_banned"):
        await message.answer("🚫 Вы заблокированы.")
        return
    if is_new:
        await _notify_new_user(message, user)
        if user.get("referrer_id"):
            try:
                await message.bot.send_message(user["referrer_id"], f"🎉 Новый реферал: <b>{html.escape(message.from_user.first_name or '')}</b>!")
            except Exception:
                pass
    text = (await db.get_setting("welcome_text") or "Привет, {name}!").replace("{name}", html.escape(message.from_user.first_name or "друг"))
    await send_or_edit(message, text, reply_markup=await kb.main_menu_kb(), image_id=(await db.get_setting("welcome_image")) or None)

@router.callback_query(F.data == "main_menu")
async def main_menu(call: CallbackQuery):
    text = (await db.get_setting("welcome_text") or "Привет, {name}!").replace("{name}", html.escape(call.from_user.first_name or "друг"))
    await send_or_edit(call, text, reply_markup=await kb.main_menu_kb(), image_id=(await db.get_setting("welcome_image")) or None)

@router.callback_query(F.data == "catalog")
async def catalog(call: CallbackQuery):
    cats = await dx.get_cats(0)
    if not cats:
        await call.answer("😔 Каталог пуст", show_alert=True)
        return
    text = (await db.get_setting("catalog_text")) or "📁 <b>Выберите категорию:</b>"
    await send_or_edit(call, text, reply_markup=kb.catalog_kb(cats, await dx.get_cols("cols_cats", 1)),
                       image_id=(await db.get_setting("catalog_image")) or None)

@router.callback_query(F.data.startswith("cat:"))
async def show_cat(call: CallbackQuery):
    cid = int(call.data.split(":")[1])
    cat = await dx.get_cat(cid)
    if not cat:
        await call.answer("Не найдено", show_alert=True)
        return
    subs = await dx.get_cats(cid)
    prods = [p for p in await dx.get_prods(cid) if await db.get_available_items_count(p["id"]) > 0]
    if not subs and not prods:
        await call.answer("😔 Здесь пока пусто", show_alert=True)
        return
    text = f"<b>{dx.title_html(cat)}</b>"
    if cat.get("description"):
        text += f"\n\n{cat['description']}"
    parent = int(cat.get("parent_id") or 0)
    back = "catalog" if parent == 0 else f"cat:{parent}"
    mk = kb.category_kb(subs, prods, await dx.get_cols("cols_cats", 1), await dx.get_cols("cols_prods", 1), back)
    await send_or_edit(call, text, reply_markup=mk, image_id=cat.get("image_id") or None)

@router.callback_query(F.data.startswith("product:"))
async def show_prod(call: CallbackQuery):
    pid = int(call.data.split(":")[1])
    prod = await dx.get_prod(pid)
    if not prod:
        await call.answer("Не найден", show_alert=True)
        return
    stock = await db.get_available_items_count(pid)
    lp, ls, lu = await get_label("label_price"), await get_label("label_stock"), await get_label("label_unit")
    text = f"<b>{dx.title_html(prod, '📦')}</b>"
    if prod.get("description"):
        text += f"\n\n{prod['description']}"
    text += f"\n\n{lp} <b>{prod['price']}$</b>\n{ls} <b>{stock} {lu}</b>"
    await send_or_edit(call, text, reply_markup=await kb.product_detail_kb(pid, prod["category_id"]), image_id=prod.get("image_id") or None)

@router.callback_query(F.data == "profile")
async def profile(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    if not user:
        await call.answer("Нажмите /start", show_alert=True)
        return
    orders = await db.get_user_orders(call.from_user.id)
    refs = await db.get_user_referrals(call.from_user.id)
    text = await T("tpl_profile",
                   id=user["user_id"], name=html.escape(user.get("first_name") or ""),
                   username=("@" + call.from_user.username) if call.from_user.username else "—",
                   balance=money(user.get("balance", 0)), ref_balance=money(user.get("ref_balance", 0)),
                   spent=money(user.get("total_spent", 0)), earned=money(user.get("total_earned", 0)),
                   orders=len(orders), refs=len(refs))
    await send_or_edit(call, text, reply_markup=await kb.profile_kb2(), image_id=(await db.get_setting("profile_image")) or None)

async def _ref_screen(call, key, back):
    user = await db.get_user(call.from_user.id)
    if not user:
        await call.answer("Нажмите /start", show_alert=True)
        return
    refs = await db.get_user_referrals(call.from_user.id)
    link = await ref_link(call.bot, call.from_user.id)
    text = await T(key, id=call.from_user.id, name=html.escape(call.from_user.first_name or ""),
                   link=link, percent=f"{REFERRAL_PERCENT:g}", refs=len(refs),
                   ref_balance=money(user.get("ref_balance", 0)), earned=money(user.get("total_earned", 0)),
                   min_withdraw=f"{MIN_WITHDRAW:g}")
    await send_or_edit(call, text, reply_markup=await kb.referral_kb2(back, link),
                       image_id=(await db.get_setting("referral_image")) or None)

@router.callback_query(F.data == "referral")
async def referral(call: CallbackQuery):
    await _ref_screen(call, "tpl_referral", "main_menu")

@router.callback_query(F.data == "ref_profile")
async def referral_profile(call: CallbackQuery):
    await _ref_screen(call, "tpl_referral_profile", "profile")

@router.callback_query(F.data == "my_orders")
async def my_orders(call: CallbackQuery):
    orders = await db.get_user_orders(call.from_user.id, limit=20)
    text = "📋 <b>Мои покупки</b>\n\n" + ("😔 Пока нет покупок" if not orders else "\n".join([f"✅ {html.escape(str(o.get('product_name') or '?'))} - {o['amount']}$ ({str(o['created_at'])[:10]})" for o in orders]))
    await send_or_edit(call, text, reply_markup=kb.back_only_kb("profile"))

@router.callback_query(F.data == "faq")
async def faq(call: CallbackQuery):
    await send_or_edit(call, await db.get_setting("faq_text") or "FAQ", reply_markup=kb.back_only_kb(), image_id=(await db.get_setting("faq_image")) or None)

@router.callback_query(F.data == "support")
async def support(call: CallbackQuery):
    await send_or_edit(call, await db.get_setting("support_text") or "Поддержка", reply_markup=kb.back_only_kb())

@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()
