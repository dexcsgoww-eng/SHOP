import html
import database as db

DEFAULTS = {
    "tpl_profile": "👤 <b>Мой профиль</b>\n\n🆔 ID: <code>{id}</code>\n👤 {name}\n\n💳 Баланс: <b>{balance}$</b>\n💰 Реф. баланс: <b>{ref_balance}$</b>\n💸 Потрачено: <b>{spent}$</b>\n💵 Заработано: <b>{earned}$</b>\n\n🛒 Покупок: <b>{orders}</b>\n👥 Рефералов: <b>{refs}</b>",
    "tpl_referral": "👥 <b>Реферальная программа</b>\n\nПриглашай друзей и получай <b>{percent}%</b> с каждой их покупки!\n\n🔗 Твоя ссылка:\n<code>{link}</code>\n\n👥 Рефералов: <b>{refs}</b>\n💰 Реф. баланс: <b>{ref_balance}$</b>\n💵 Всего заработано: <b>{earned}$</b>\n💸 Мин. вывод: <b>{min_withdraw}$</b>",
    "tpl_referral_profile": "👥 <b>Моя рефералка</b>\n\n🔗 Ссылка для друзей:\n<code>{link}</code>\n\n💸 Процент: <b>{percent}%</b>\n👥 Рефералов: <b>{refs}</b>\n💰 Реф. баланс: <b>{ref_balance}$</b>\n💵 Заработано: <b>{earned}$</b>",
    "tpl_pay_select": "💳 <b>Оплата</b>\n\n📦 {product}\n💰 Цена: <b>{price}$</b>\n💳 Ваш баланс: <b>{balance}$</b>\n\nВыберите способ оплаты:",
    "tpl_pay_balance": "💰 <b>Оплата с баланса</b>\n\n📦 {product}\n💵 Цена: <b>{price}$</b>\n💳 Баланс после покупки: <b>{balance_after}$</b>\n\nПодтвердите покупку:",
    "tpl_pay_invoice": "🧾 <b>Счёт создан</b>\n\n📦 {product}\n💰 <b>{price}$ USDT</b>\n💳 {method}\n\n1️⃣ Нажмите «Оплатить»\n2️⃣ Оплатите счёт\n3️⃣ Нажмите «Проверить»",
    "tpl_pay_manual": "💎 <b>Оплата USDT TRC20</b>\n\n📦 {product}\n💵 К оплате: <b>{price} USDT</b>\n📩 Адрес:\n<code>{address}</code>\n\n{instructions}\n\nПосле перевода пришлите сюда <b>TxID</b> текстом или <b>скриншот</b>.",
    "tpl_pay_manual_created": "✅ <b>Заявка на оплату #{id} создана!</b>\n\n📦 {product}\n💵 {amount} USDT TRC20\n\nТовар придёт сюда автоматически после подтверждения админом.",
    "tpl_purchase_done": "✅ <b>Оплата прошла!</b>\n\n📦 {product}\n\n📄 <b>Ваш товар:</b>\n<code>{content}</code>",
    "tpl_topup_menu": "💰 <b>Пополнение баланса</b>\n\n💳 Баланс: <b>{balance}$</b>\n\nВыберите способ:",
    "tpl_topup_amount": "💰 <b>Пополнение через {method}</b>\n\nВыберите сумму:",
    "tpl_topup_invoice": "💰 <b>Пополнение через {method}</b>\n\n💵 Сумма: <b>{amount}$</b>\n\nОплатите и нажмите «Проверить»",
    "tpl_topup_success": "✅ <b>Баланс пополнен!</b>\n\n💵 +{amount}$\n💳 Баланс: <b>{balance}$</b>",
    "tpl_topup_manual": "💎 <b>Пополнение USDT TRC20</b>\n\n📩 Адрес:\n<code>{address}</code>\n\n{instructions}\n\n✏️ Введите сумму в $:",
    "tpl_topup_manual_send": "💎 Отправьте <b>{amount}$ USDT TRC20</b> на:\n<code>{address}</code>\n\nПришлите TxID текстом или скриншот.",
    "tpl_topup_manual_created": "✅ <b>Заявка на пополнение #{id} создана!</b>\n💵 {amount}$ USDT TRC20\nБаланс пополнится после подтверждения админом.",
}

_P_USER = {"id": "ID пользователя", "name": "имя"}
INFO = {
    "tpl_profile": ("👤 Профиль", {**_P_USER, "username": "@username", "balance": "баланс", "ref_balance": "реф. баланс", "spent": "потрачено", "earned": "заработано", "orders": "кол-во покупок", "refs": "кол-во рефералов"}),
    "tpl_referral": ("👥 Рефералка (главное меню)", {**_P_USER, "link": "реф. ссылка", "percent": "процент", "refs": "рефералов", "ref_balance": "реф. баланс", "earned": "заработано", "min_withdraw": "мин. вывод"}),
    "tpl_referral_profile": ("👥 Рефералка (из профиля)", {**_P_USER, "link": "реф. ссылка", "percent": "процент", "refs": "рефералов", "ref_balance": "реф. баланс", "earned": "заработано", "min_withdraw": "мин. вывод"}),
    "tpl_pay_select": ("💳 Выбор способа оплаты", {"product": "товар", "price": "цена", "balance": "баланс"}),
    "tpl_pay_balance": ("💰 Оплата с баланса", {"product": "товар", "price": "цена", "balance": "баланс", "balance_after": "баланс после"}),
    "tpl_pay_invoice": ("🧾 Счёт CryptoBot / xRocket", {"product": "товар", "price": "цена", "method": "способ оплаты"}),
    "tpl_pay_manual": ("💎 Оплата товара USDT", {"product": "товар", "price": "цена", "address": "адрес", "instructions": "инструкция"}),
    "tpl_pay_manual_created": ("✅ Заявка на оплату создана", {"id": "номер заявки", "product": "товар", "amount": "сумма"}),
    "tpl_purchase_done": ("📄 Выдача товара", {"product": "товар", "content": "данные товара"}),
    "tpl_topup_menu": ("💰 Пополнение: меню", {"balance": "баланс"}),
    "tpl_topup_amount": ("💵 Пополнение: выбор суммы", {"method": "способ"}),
    "tpl_topup_invoice": ("🧾 Пополнение: счёт", {"method": "способ", "amount": "сумма"}),
    "tpl_topup_success": ("✅ Пополнение: успешно", {"amount": "сумма", "balance": "баланс"}),
    "tpl_topup_manual": ("💎 Пополнение USDT: адрес", {"address": "адрес", "instructions": "инструкция"}),
    "tpl_topup_manual_send": ("💎 Пополнение USDT: отправка", {"amount": "сумма", "address": "адрес"}),
    "tpl_topup_manual_created": ("✅ Пополнение USDT: заявка", {"id": "номер заявки", "amount": "сумма"}),
}

async def T(key, **vals):
    tpl = ((await db.get_setting(key)) or "").strip() or DEFAULTS.get(key, "")
    for k, v in vals.items():
        tpl = tpl.replace("{" + k + "}", str(v))
    return tpl

def pname(prod):
    if not prod:
        return "?"
    return prod.get("name_html") or html.escape(str(prod.get("name") or "?"))

def money(v):
    try:
        return f"{float(v):.2f}"
    except Exception:
        return str(v)

_UN = None
async def bot_username(bot):
    global _UN
    if not _UN:
        try:
            _UN = (await bot.get_me()).username
        except Exception:
            from config import BOT_USERNAME
            _UN = (BOT_USERNAME or "").lstrip("@")
    return _UN

async def ref_link(bot, uid):
    return f"https://t.me/{await bot_username(bot)}?start={uid}"
