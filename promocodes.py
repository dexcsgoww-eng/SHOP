import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from config import ADMIN_IDS
import database as db
from states import AddPromocode, UsePromocode
from utils import send_or_edit

router = Router()
def _a(uid): return uid in ADMIN_IDS
def B(t, d=None, u=None):
    kw = {"text": t}; kw["url" if u else "callback_data"] = u or d; return InlineKeyboardButton(**kw)
def M(r): return InlineKeyboardMarkup(inline_keyboard=r)

@router.callback_query(F.data == "adm:promos")
async def adm_promos(call: CallbackQuery):
    if not _a(call.from_user.id): return
    ps = await db.get_all_promocodes()
    rows = []
    for p in ps:
        v = f"{p['amount']}$" if p["type"] == "balance" else f"{p['discount_percent']}%"
        rows.append([B(f"{'🟢' if p['is_active'] else '🔴'} {p['code']} | {v} | {p['uses_count']}/{p['max_uses'] or '∞'}", f"adm:promo:{p['id']}")])
    rows += [[B("➕ Создать", "adm:promo_add")], [B("◀️ Назад", "admin_panel")]]
    await send_or_edit(call, f"🎁 <b>Промокоды</b> ({len(ps)})", reply_markup=M(rows))

@router.callback_query(F.data == "adm:promo_add")
async def pa_start(call: CallbackQuery, state: FSMContext):
    if not _a(call.from_user.id): return
    await state.set_state(AddPromocode.code)
    await send_or_edit(call, "🎁 Введите <b>код</b>:", reply_markup=M([[B("❌ Отмена", "adm:promos")]]))

@router.message(AddPromocode.code)
async def pa_code(m: Message, state: FSMContext):
    if not _a(m.from_user.id): return
    c = m.text.strip().upper()
    if len(c) < 3 or len(c) > 30: await m.answer("❌ 3-30 символов"); return
    if await db.get_promocode(code=c): await m.answer("❌ Уже есть"); return
    await state.update_data(code=c); await state.set_state(AddPromocode.ptype)
    await m.answer("Тип:", reply_markup=M([[B("💰 Баланс", "pt:balance")], [B("🎯 Скидка %", "pt:discount")], [B("❌", "adm:promos")]]))

@router.callback_query(F.data.startswith("pt:"), AddPromocode.ptype)
async def pa_type(call: CallbackQuery, state: FSMContext):
    if not _a(call.from_user.id): return
    t = call.data.split(":")[1]
    await state.update_data(ptype=t); await state.set_state(AddPromocode.amount)
    await call.message.edit_text("💰 Сумма $:" if t == "balance" else "🎯 Процент (1-100):", reply_markup=M([[B("❌", "adm:promos")]]))

@router.message(AddPromocode.amount)
async def pa_amt(m: Message, state: FSMContext):
    if not _a(m.from_user.id): return
    try:
        v = float(m.text.replace(",", "."))
        if v <= 0: raise ValueError
    except ValueError: await m.answer("❌ Число > 0"); return
    d = await state.get_data()
    if d["ptype"] == "balance": await state.update_data(amount=v, discount_percent=0)
    else:
        if v > 100: await m.answer("❌ Макс 100%"); return
        await state.update_data(amount=0, discount_percent=int(v))
    await state.set_state(AddPromocode.max_uses)
    await m.answer("🔢 Макс. использований (0=∞):", reply_markup=M([[B("❌", "adm:promos")]]))

@router.message(AddPromocode.max_uses)
async def pa_uses(m: Message, state: FSMContext):
    if not _a(m.from_user.id): return
    try:
        v = int(m.text)
        if v < 0: raise ValueError
    except ValueError: await m.answer("❌ ≥ 0"); return
    await state.update_data(max_uses=v); d = await state.get_data()
    if d["ptype"] == "discount":
        await state.set_state(AddPromocode.min_purchase)
        await m.answer("💵 Мин. сумма (0=без):", reply_markup=M([[B("❌", "adm:promos")]]))
    else:
        await state.set_state(AddPromocode.expires_days)
        await m.answer("⏰ Дней (0=∞):", reply_markup=M([[B("❌", "adm:promos")]]))

@router.message(AddPromocode.min_purchase)
async def pa_min(m: Message, state: FSMContext):
    if not _a(m.from_user.id): return
    try:
        v = float(m.text.replace(",", "."))
        if v < 0: raise ValueError
    except ValueError: await m.answer("❌ ≥ 0"); return
    await state.update_data(min_purchase=v); await state.set_state(AddPromocode.expires_days)
    await m.answer("⏰ Дней (0=∞):", reply_markup=M([[B("❌", "adm:promos")]]))

@router.message(AddPromocode.expires_days)
async def pa_exp(m: Message, state: FSMContext):
    if not _a(m.from_user.id): return
    try:
        d = int(m.text)
        if d < 0: raise ValueError
    except ValueError: await m.answer("❌ ≥ 0"); return
    data = await state.get_data(); await state.clear()
    exp = (datetime.now() + timedelta(days=d)).isoformat() if d > 0 else None
    pid = await db.create_promocode(code=data["code"], type_=data["ptype"], amount=data.get("amount",0),
        discount_percent=data.get("discount_percent",0), max_uses=data["max_uses"],
        min_purchase=data.get("min_purchase",0), expires_at=exp, created_by=m.from_user.id)
    if pid:
        v = f"{data.get('amount',0)}$" if data["ptype"]=="balance" else f"{data.get('discount_percent',0)}%"
        await m.answer(f"✅ <code>{data['code']}</code> | {v} | {data['max_uses'] or '∞'} | {d or '∞'}д", reply_markup=M([[B("◀️", "adm:promos")]]))
    else: await m.answer("❌ Ошибка")

@router.callback_query(F.data.startswith("adm:promo:"))
async def p_detail(call: CallbackQuery):
    if not _a(call.from_user.id): return
    pid = int(call.data.split(":")[2])
    p = await db.get_promocode(promo_id=pid)
    if not p: await call.answer("Не найден", show_alert=True); return
    v = f"{p['amount']}$" if p["type"]=="balance" else f"{p['discount_percent']}%"
    await send_or_edit(call, f"🎁 <b>{p['code']}</b>\n{p['type']} | {v}\n{p['uses_count']}/{p['max_uses'] or '∞'}\n{'🟢' if p['is_active'] else '🔴'}",
        reply_markup=M([[B("🔄", f"adm:promo_tog:{pid}")], [B("🗑", f"adm:promo_del:{pid}")], [B("◀️", "adm:promos")]]))

@router.callback_query(F.data.startswith("adm:promo_tog:"))
async def p_tog(call: CallbackQuery):
    if not _a(call.from_user.id): return
    await db.toggle_promocode(int(call.data.split(":")[2])); await call.answer("✅")
    call = call.model_copy(update={"data": f"adm:promo:{call.data.split(':')[2]}"})
    await p_detail(call)

@router.callback_query(F.data.startswith("adm:promo_del:"))
async def p_del(call: CallbackQuery):
    if not _a(call.from_user.id): return
    await db.delete_promocode(int(call.data.split(":")[2])); await call.answer("🗑"); await adm_promos(call)

@router.callback_query(F.data == "promo_use")
async def u_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(UsePromocode.code)
    await send_or_edit(call, "🎁 Введите промокод:", reply_markup=M([[B("❌", "profile")]]))

@router.message(UsePromocode.code)
async def u_apply(m: Message, state: FSMContext):
    await state.clear()
    r = await db.apply_promocode(m.text.strip().upper(), m.from_user.id)
    if not r["ok"]: await m.answer(f"❌ {r['error']}", reply_markup=M([[B("◀️", "profile")]])); return
    p = r["promo"]
    if p["type"] == "balance":
        await db.use_promocode(p["id"], m.from_user.id); await db.add_balance(m.from_user.id, p["amount"])
        await m.answer(f"✅ +<b>{p['amount']}$</b>!", reply_markup=M([[B("◀️", "profile")]]))
    else:
        await db.set_active_promo(m.from_user.id, p["id"], p["discount_percent"])
        await m.answer(f"✅ Скидка <b>{p['discount_percent']}%</b> активна!", reply_markup=M([[B("🛍", "catalog")], [B("◀️", "profile")]]))

@router.message(Command("promo"))
async def cmd_promo(m: Message, state: FSMContext):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        await state.set_state(UsePromocode.code)
        await m.answer("🎁 Введите промокод:", reply_markup=M([[B("❌", "profile")]])); return
    m.text = parts[1]; await u_apply(m, state)

@router.callback_query(F.data.startswith("promo_clear:"))
async def p_clear(call: CallbackQuery):
    await db.clear_active_promo(call.from_user.id)
    await call.answer("Скидка отменена", show_alert=True)
    call = call.model_copy(update={"data": f"product:{call.data.split(':')[1]}"})
    from handlers.user import show_product; await show_product(call)
