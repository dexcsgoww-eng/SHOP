from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
import database as db, keyboards as kb
from config import BOT_USERNAME, REFERRAL_PERCENT, MIN_WITHDRAW, ADMIN_IDS
from states import Withdraw
from utils import send_or_edit
router = Router()
@router.callback_query(F.data == "referral")
async def referral_menu(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    refs = await db.get_user_referrals(call.from_user.id)
    link = f"https://t.me/{BOT_USERNAME}?start={call.from_user.id}"
    text = f"👥 <b>Реферальная программа</b>\n\n💰 Процент: <b>{REFERRAL_PERCENT}%</b>\n💵 Заработано: <b>{user['total_earned']:.2f}$</b>\n💳 К выводу: <b>{user['ref_balance']:.2f}$</b>\n👥 Рефералов: <b>{len(refs)}</b>\n💸 Минимум вывода: <b>{MIN_WITHDRAW}$</b>\n\n🔗 Ваша ссылка:\n<code>{link}</code>"
    await send_or_edit(call, text, reply_markup=kb.referral_kb())
@router.callback_query(F.data == "withdraw_start")
async def wd_start(call: CallbackQuery, state: FSMContext):
    user = await db.get_user(call.from_user.id)
    if user["ref_balance"] < MIN_WITHDRAW:
        await call.answer(f"❌ Минимум {MIN_WITHDRAW}$, у вас {user['ref_balance']:.2f}$", show_alert=True)
        return
    await state.set_state(Withdraw.method)
    await send_or_edit(call, f"💸 <b>Вывод</b>\n\nДоступно: <b>{user['ref_balance']:.2f}$</b>", reply_markup=kb.withdraw_method_kb())
@router.callback_query(F.data.startswith("wd_method:"), Withdraw.method)
async def wd_method(call: CallbackQuery, state: FSMContext):
    await state.update_data(method=call.data.split(":")[1])
    await state.set_state(Withdraw.address)
    await send_or_edit(call, "📩 Отправьте <b>адрес / ID для получения выплаты</b>:", reply_markup=kb.back_only_kb("referral"))
@router.message(Withdraw.address)
async def wd_addr(message: Message, state: FSMContext):
    await state.update_data(address=message.text.strip())
    await state.set_state(Withdraw.amount)
    user = await db.get_user(message.from_user.id)
    await message.answer(f"💰 Введите сумму, максимум {user['ref_balance']:.2f}$:")
@router.message(Withdraw.amount)
async def wd_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
    except Exception:
        await message.answer("❌ Неверная сумма")
        return
    user = await db.get_user(message.from_user.id)
    if amount < MIN_WITHDRAW or amount > user["ref_balance"]:
        await message.answer("❌ Неверная сумма или недостаточно средств")
        return
    data = await state.get_data()
    await state.clear()
    if not await db.subtract_ref_balance(message.from_user.id, amount):
        await message.answer("❌ Ошибка списания")
        return
    wid = await db.create_withdrawal(message.from_user.id, amount, data["method"], data["address"])
    await message.answer(f"✅ <b>Заявка #{wid} создана</b>\n\n💰 {amount}$\n💳 {data['method']}\n📩 {data['address']}", reply_markup=kb.back_only_kb("referral"))
    for aid in ADMIN_IDS:
        try:
            await message.bot.send_message(aid, f"💸 <b>Заявка на вывод #{wid}</b>\n👤 {message.from_user.first_name} (<code>{message.from_user.id}</code>)\n💰 {amount}$\n💳 {data['method']}\n📩 {data['address']}")
        except Exception:
            pass
