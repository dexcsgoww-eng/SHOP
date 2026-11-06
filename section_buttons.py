import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from config import ADMIN_IDS
import database as db
from states import AddSectionButton, EditSectionButton
from utils import send_or_edit

router = Router()
SECTIONS = {"main_menu": "🏠 Главное меню", "profile": "👤 Профиль", "catalog": "🛍 Каталог",
            "faq": "ℹ️ FAQ", "support": "💬 Поддержка", "referral": "👥 Рефералка"}
def _a(uid): return uid in ADMIN_IDS
def B(t, d=None, u=None):
    kw = {"text": t}; kw["url" if u else "callback_data"] = u or d; return InlineKeyboardButton(**kw)
def M(r): return InlineKeyboardMarkup(inline_keyboard=r)

@router.callback_query(F.data == "adm:sbtns")
async def sb_main(call: CallbackQuery):
    if not _a(call.from_user.id): return
    rows = [[B(f"{l} ({len(await db.sb_list(k))})", f"adm:sb_sec:{k}")] for k, l in SECTIONS.items()]
    rows.append([B("◀️ Назад", "admin_panel")])
    await send_or_edit(call, "🔗 <b>Кнопки разделов</b>", reply_markup=M(rows))

@router.callback_query(F.data.startswith("adm:sb_sec:"))
async def sb_sec(call: CallbackQuery):
    if not _a(call.from_user.id): return
    sec = call.data.split(":")[2]; btns = await db.sb_list(sec)
    rows = [[B(f"{'🟢' if b['is_active'] else '🔴'} {b['text'][:40]}", f"adm:sb:{b['id']}")] for b in btns]
    rows += [[B("➕ Добавить", f"adm:sb_add:{sec}")], [B("◀️ Назад", "adm:sbtns")]]
    await send_or_edit(call, f"🔗 <b>{SECTIONS.get(sec,sec)}</b> ({len(btns)})", reply_markup=M(rows))

@router.callback_query(F.data.startswith("adm:sb_add:"))
async def sb_add_s(call: CallbackQuery, state: FSMContext):
    if not _a(call.from_user.id): return
    sec = call.data.split(":")[2]
    await state.set_state(AddSectionButton.text); await state.update_data(section=sec)
    await send_or_edit(call, "📝 Текст кнопки:", reply_markup=M([[B("❌", f"adm:sb_sec:{sec}")]]))

@router.message(AddSectionButton.text)
async def sb_add_t(m: Message, state: FSMContext):
    if not _a(m.from_user.id): return
    t = m.text.strip()
    if not t or len(t) > 64: await m.answer("❌ 1-64"); return
    await state.update_data(text=t); await state.set_state(AddSectionButton.data)
    await m.answer("🔗 URL или callback_data:", reply_markup=M([[B("❌", "adm:sbtns")]]))

@router.message(AddSectionButton.data)
async def sb_add_d(m: Message, state: FSMContext):
    if not _a(m.from_user.id): return
    d = await state.get_data(); v = m.text.strip()
    url = v if v.startswith(("http://","https://","tg://")) else None
    bid = await db.sb_add(d["section"], d["text"], url=url, callback_data=None if url else v)
    await state.clear()
    await m.answer("✅ Добавлена!", reply_markup=M([[B("⚙️", f"adm:sb:{bid}")], [B("◀️", f"adm:sb_sec:{d['section']}")]]))

@router.callback_query(F.data.startswith("adm:sb:"))
async def sb_det(call: CallbackQuery):
    if not _a(call.from_user.id): return
    bid = int(call.data.split(":")[2]); b = await db.sb_get(bid)
    if not b: await call.answer("Не найдено", show_alert=True); return
    await send_or_edit(call, f"🔗 <b>#{b['id']}</b>\n📝 {b['text']}\n🔗 {b['url'] or '—'}\n📊 {b['callback_data'] or '—'}\n{'🟢' if b['is_active'] else '🔴'}",
        reply_markup=M([[B("✏️ Текст", f"adm:sb_ed:text:{bid}"), B("✏️ Ссылка", f"adm:sb_ed:data:{bid}")],
            [B("🔄", f"adm:sb_tog:{bid}")], [B("🗑", f"adm:sb_del:{bid}")], [B("◀️", f"adm:sb_sec:{b['section']}")]]))

@router.callback_query(F.data.startswith("adm:sb_tog:"))
async def sb_tog(call: CallbackQuery):
    if not _a(call.from_user.id): return
    bid = int(call.data.split(":")[2]); await db.sb_toggle(bid); await call.answer("✅")
    call = call.model_copy(update={"data": f"adm:sb:{bid}"}); await sb_det(call)

@router.callback_query(F.data.startswith("adm:sb_del:"))
async def sb_del(call: CallbackQuery):
    if not _a(call.from_user.id): return
    bid = int(call.data.split(":")[2]); b = await db.sb_get(bid)
    sec = b["section"] if b else "main_menu"; await db.sb_delete(bid); await call.answer("🗑")
    call = call.model_copy(update={"data": f"adm:sb_sec:{sec}"}); await sb_sec(call)

@router.callback_query(F.data.startswith("adm:sb_ed:"))
async def sb_ed(call: CallbackQuery, state: FSMContext):
    if not _a(call.from_user.id): return
    _, _, field, bid = call.data.split(":")
    await state.set_state(EditSectionButton.value); await state.update_data(field=field, bid=int(bid))
    await send_or_edit(call, "✏️ Новое значение:", reply_markup=M([[B("❌", f"adm:sb:{bid}")]]))

@router.message(EditSectionButton.value)
async def sb_ed_s(m: Message, state: FSMContext):
    if not _a(m.from_user.id): return
    d = await state.get_data(); await state.clear(); v = m.text.strip()
    if d["field"] == "text": await db.sb_update(d["bid"], text=v)
    elif v.startswith(("http://","https://","tg://")): await db.sb_update(d["bid"], url=v, callback_data=None)
    else: await db.sb_update(d["bid"], url=None, callback_data=v)
    await m.answer("✅", reply_markup=M([[B("⚙️", f"adm:sb:{d['bid']}")]]))
