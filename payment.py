import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
import database as db
from texts import T, money, pname
from keyboards import check_payment_kb, manual_cancel_kb, topup_check_kb, topup_amount_kb
import xrocket_pay
try:
    from config import XROCKET_TOKEN, XROCKET_API_URL, REFERRAL_PERCENT
except ImportError:
    XROCKET_TOKEN = ""; XROCKET_API_URL = ""; REFERRAL_PERCENT = 0

router = Router()
logger = logging.getLogger(__name__)

async def _di(uid, pid, base):
    i = await db.calculate_price_with_promo(uid, pid, base)
    return i["final_price"], i["discount"], i["promo_code"], i["promo_id"]

async def _fp(uid, pid_):
    if pid_:
        await db.use_promocode(pid_, uid)
        await db.clear_active_promo(uid)

async def _ref(uid, amount, bot):
    if not REFERRAL_PERCENT: return
    u = await db.get_user(uid)
    if not u or not u.get("referrer_id"): return
    r = round(amount * REFERRAL_PERCENT / 100, 4)
    if r > 0:
        await db.add_ref_balance(u["referrer_id"], r)
        try: await bot.send_message(u["referrer_id"], f"💰 +{r:.4f}$ от реферала!")
        except Exception: pass

def _dl(d, c):
    return f"\n🎁 Скидка: <b>−{d:.2f}$</b> (<code>{c}</code>)" if d > 0 and c else ""

@router.callback_query(F.data.startswith("pay:xrocket:"))
async def cb_pay_xrocket(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) < 3: await call.answer("Ошибка", show_alert=True); return
    pid = int(parts[-1])
    prod = await db.get_product(pid)
    if not prod: await call.answer("Не найден", show_alert=True); return
    base = float(prod.get("price", 0))
    final, disc, pc, pr = await _di(call.from_user.id, pid, base)
    inv = xrocket_pay.create_xrocket_invoice(final, description=f"Buy: {prod.get('name','?')}")
    if not inv or not inv.get("invoice_id"):
        try: await call.message.edit_text(f"❌ Ошибка XRocket.\nТокен: {'✅' if XROCKET_TOKEN else '❌'}")
        except Exception: await call.message.answer("❌ Ошибка XRocket")
        await call.answer("Ошибка", show_alert=True); return
    pay_id = f"{inv['invoice_id']}|promo:{pr}" if pr else str(inv["invoice_id"])
    await db.create_order(call.from_user.id, pid, final, "xrocket", pay_id)
    ps = f"<s>{money(base)}</s> → <b>{money(final)}</b>" if disc > 0 else money(final)
    text = await T("tpl_pay_invoice", product=pname(prod), price=ps, method="XRocket")
    text += _dl(disc, pc)
    kb = check_payment_kb("xrocket", inv["invoice_id"], inv.get("pay_url") or "#", pid)
    try: await call.message.edit_text(text, reply_markup=kb)
    except Exception: await call.message.answer(text, reply_markup=kb)
    await call.answer("Счёт создан ✅")

@router.callback_query(F.data.startswith("check:xrocket:"))
async def cb_check_xrocket(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) < 4: await call.answer("Ошибка", show_alert=True); return
    inv_id, pid = parts[2], int(parts[3])
    status = xrocket_pay.check_xrocket_invoice(inv_id)
    if status in ("paid", "completed", "success", "confirmed"):
        order = await db.get_order_by_payment(inv_id)
        if not order: order = await db.get_order_by_payment_prefix(inv_id)
        if order and order.get("status") == "pending":
            res = await db.buy_item(pid, call.from_user.id)
            if res:
                item_id, content = res
                await db.complete_order(order["id"], item_id)
                pr = None
                if "|promo:" in order.get("payment_id", ""):
                    try: pr = int(order["payment_id"].split("|promo:")[1])
                    except Exception: pass
                await _fp(call.from_user.id, pr)
                await _ref(call.from_user.id, order["amount"], call.bot)
                prod = await db.get_product(pid)
                msg = await T("tpl_purchase_done", product=pname(prod), content=content)
                try: await call.message.edit_text(msg)
                except Exception: await call.message.answer(msg)
                await call.answer("Оплачено! ✅", show_alert=True); return
        await call.answer("Оплата получена ✅", show_alert=True)
    elif status is None or status == "unknown":
        await call.answer("Пока не найдено", show_alert=False)
    else:
        await call.answer(f"Статус: {status}", show_alert=False)

@router.callback_query(F.data.startswith("pay:crypto_bot:"))
async def cb_pay_crypto(call: CallbackQuery):
    await call.answer("CryptoBot отключён", show_alert=True)

@router.callback_query(F.data.startswith("pay:balance:"))
async def cb_pay_balance(call: CallbackQuery):
    parts = call.data.split(":")
    pid = int(parts[-1]) if len(parts) >= 3 else 0
    prod = await db.get_product(pid)
    if not prod: await call.answer("Не найден", show_alert=True); return
    user = await db.get_user(call.from_user.id)
    base = float(prod.get("price", 0))
    final, disc, pc, pr = await _di(call.from_user.id, pid, base)
    if (user.get("balance") or 0) < final:
        await call.answer(f"Недостаточно ({final}$)", show_alert=True); return
    if await db.get_available_items_count(pid) == 0:
        await call.answer("❌ Закончился", show_alert=True); return
    ok = await db.subtract_balance(call.from_user.id, final)
    if not ok: await call.answer("❌ Ошибка", show_alert=True); return
    res = await db.buy_item(pid, call.from_user.id)
    if not res:
        await db.add_balance(call.from_user.id, final)
        await call.answer("❌ Закончился, деньги возвращены", show_alert=True); return
    item_id, content = res
    oid = await db.create_order(call.from_user.id, pid, final, "balance", f"bal_{call.from_user.id}_{item_id}")
    await db.complete_order(oid, item_id)
    await _fp(call.from_user.id, pr)
    await _ref(call.from_user.id, final, call.bot)
    msg = await T("tpl_purchase_done", product=pname(prod), content=content) + _dl(disc, pc)
    try: await call.message.edit_text(msg)
    except Exception: await call.message.answer(msg)
    await call.answer("Куплено ✅")

@router.callback_query(F.data.startswith("pay:manual:"))
async def cb_pay_manual(call: CallbackQuery):
    parts = call.data.split(":")
    pid = int(parts[-1])
    prod = await db.get_product(pid)
    if not prod: await call.answer("Не найден", show_alert=True); return
    base = float(prod.get("price", 0))
    final, disc, pc, pr = await _di(call.from_user.id, pid, base)
    addr = await db.get_setting("manual_usdt_address", "TYourTRC20Wallet")
    inst = await db.get_setting("manual_instructions", "Пришлите TxID.")
    text = await T("tpl_pay_manual", product=pname(prod), price=final, address=addr, instructions=inst) + _dl(disc, pc)
    try: await call.message.edit_text(text, reply_markup=manual_cancel_kb())
    except Exception: await call.message.answer(text, reply_markup=manual_cancel_kb())
    await call.answer("✅")

@router.callback_query(F.data.startswith("topup_method:xrocket"))
async def cb_topup_xr(call: CallbackQuery):
    kb = topup_amount_kb("xrocket")
    try: await call.message.edit_text("💰 Сумма XRocket:", reply_markup=kb)
    except Exception: await call.message.answer("💰 Сумма XRocket:", reply_markup=kb)

@router.callback_query(F.data.startswith("topup_amt:xrocket:"))
async def cb_topup_amt(call: CallbackQuery):
    a = call.data.split(":")[-1]
    if a == "custom": await call.answer("Введите сумму в чат", show_alert=True); return
    try: amount = float(a)
    except Exception: await call.answer("Неверная сумма", show_alert=True); return
    inv = xrocket_pay.create_xrocket_invoice(amount, description="Topup")
    if not inv or not inv.get("invoice_id"):
        try: await call.message.edit_text("❌ Ошибка XRocket")
        except Exception: await call.message.answer("❌ Ошибка")
        await call.answer("Ошибка", show_alert=True); return
    text = await T("tpl_topup_invoice", method="XRocket", amount=money(amount))
    kb = topup_check_kb("xrocket", inv["invoice_id"], inv.get("pay_url") or "#")
    try: await call.message.edit_text(text, reply_markup=kb)
    except Exception: await call.message.answer(text, reply_markup=kb)
    await call.answer("✅")

@router.callback_query(F.data.startswith("topup_check:xrocket:"))
async def cb_topup_chk(call: CallbackQuery):
    status = xrocket_pay.check_xrocket_invoice(call.data.split(":")[-1])
    if status in ("paid", "completed", "success", "confirmed"):
        try: await call.message.edit_text("✅ Пополнение получено!")
        except Exception: await call.message.answer("✅ Пополнение получено!")
        await call.answer("✅", show_alert=True)
    else:
        await call.answer(f"Статус: {status or 'не найден'}", show_alert=False)
