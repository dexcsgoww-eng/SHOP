import logging
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from config import ADMIN_IDS
import database as db
import keyboards as kb
from states import (
    AddCategory, EditCategory, AddProduct, EditProduct, UploadItems,
    Broadcast, EditText, EditImage, UserManage, AdminWithdraw
)
from utils import send_or_edit

logger = logging.getLogger(__name__)
router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await show_admin_panel(message)


@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.clear()
    await show_admin_panel(call)


async def show_admin_panel(event):
    stats = await db.get_orders_stats()
    users = await db.get_user_count()
    pending = len(await db.get_pending_withdrawals())

    text = (
        "🔐 <b>Админ-панель</b>\n\n"
        f"👥 Пользователей: <b>{users}</b>\n"
        f"🛒 Продаж: <b>{stats['count']}</b>\n"
        f"💰 Выручка: <b>{stats['total']:.2f}$</b>\n"
        f"💸 Заявок на вывод: <b>{pending}</b>"
    )
    await send_or_edit(event, text, reply_markup=kb.admin_menu_kb())


# ============ СТАТИСТИКА ============
@router.callback_query(F.data == "adm:stats")
async def adm_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    stats = await db.get_orders_stats()
    users = await db.get_user_count()
    cats = await db.get_categories(active_only=False)

    total_prods = 0
    total_stock = 0
    for cat in cats:
        prods = await db.get_products(cat["id"], active_only=False)
        total_prods += len(prods)
        for p in prods:
            total_stock += await db.get_available_items_count(p["id"])

    text = (
        "📊 <b>Полная статистика</b>\n\n"
        f"👥 Пользователей: <b>{users}</b>\n"
        f"📁 Категорий: <b>{len(cats)}</b>\n"
        f"📦 Товаров: <b>{total_prods}</b>\n"
        f"🗃 Позиций в наличии: <b>{total_stock}</b>\n\n"
        f"🛒 Продаж: <b>{stats['count']}</b>\n"
        f"💰 Выручка: <b>{stats['total']:.2f}$</b>"
    )
    await send_or_edit(call, text, reply_markup=kb.back_only_kb("admin_panel"))


# ============ КАТЕГОРИИ ============
@router.callback_query(F.data == "adm:cats")
async def adm_cats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cats = await db.get_categories(active_only=False)
    await send_or_edit(
        call, "📁 <b>Управление категориями</b>",
        reply_markup=kb.admin_cats_kb(cats)
    )


@router.callback_query(F.data == "adm:add_cat")
async def adm_add_cat(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AddCategory.name)
    await send_or_edit(call, "📁 Введите <b>название</b> категории:", reply_markup=kb.cancel_kb())


@router.message(AddCategory.name)
async def ac_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(name=message.text)
    await state.set_state(AddCategory.emoji)
    await message.answer("😀 Отправьте <b>эмодзи</b> (или /skip):", reply_markup=kb.cancel_kb())


@router.message(AddCategory.emoji)
async def ac_emoji(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    emoji = "📦" if message.text == "/skip" else message.text.strip()
    await state.update_data(emoji=emoji)
    await state.set_state(AddCategory.description)
    await message.answer("📝 Введите <b>описание</b> (или /skip):", reply_markup=kb.cancel_kb())


@router.message(AddCategory.description)
async def ac_desc(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    desc = "" if message.text == "/skip" else message.text
    await state.update_data(description=desc)
    await state.set_state(AddCategory.image)
    await message.answer(
        "🖼 Отправьте <b>картинку</b> для категории (или /skip):",
        reply_markup=kb.cancel_kb()
    )


@router.message(AddCategory.image, F.photo)
async def ac_image_photo(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await _finalize_category(message, state, message.photo[-1].file_id)


@router.message(AddCategory.image)
async def ac_image_skip(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text == "/skip":
        await _finalize_category(message, state, None)
    else:
        await message.answer("❌ Отправьте фото или /skip")


async def _finalize_category(message: Message, state: FSMContext, image_id):
    data = await state.get_data()
    await state.clear()
    cat_id = await db.add_category(data["name"], data["description"], data["emoji"], image_id)
    cat = await db.get_category(cat_id)
    await message.answer(
        f"✅ Категория <b>{data['emoji']} {data['name']}</b> создана!",
        reply_markup=kb.admin_cat_detail_kb(cat_id, bool(cat["is_active"]))
    )


@router.callback_query(F.data.startswith("adm:cat:"))
async def adm_cat_detail(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cat_id = int(call.data.split(":")[2])
    cat = await db.get_category(cat_id)
    if not cat:
        await call.answer("Не найдено", show_alert=True)
        return

    prods = await db.get_products(cat_id, active_only=False)
    stock = sum([await db.get_available_items_count(p["id"]) for p in prods])

    text = (
        f"{cat['emoji']} <b>{cat['name']}</b>\n\n"
        f"📝 {cat['description'] or '—'}\n"
        f"📦 Товаров: {len(prods)}\n"
        f"🗃 Позиций: {stock}\n"
        f"👁 Активна: {'Да' if cat['is_active'] else 'Нет'}"
    )

    await send_or_edit(
        call, text,
        reply_markup=kb.admin_cat_detail_kb(cat_id, bool(cat["is_active"])),
        image_id=cat.get("image_id")
    )


@router.callback_query(F.data.startswith("adm:toggle_cat:"))
async def adm_toggle_cat(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cat_id = int(call.data.split(":")[2])
    cat = await db.get_category(cat_id)
    await db.update_category(cat_id, is_active=0 if cat["is_active"] else 1)
    await call.answer("✅ Готово")
    await adm_cat_detail(call)


@router.callback_query(F.data.startswith("adm:del_cat:"))
async def adm_del_cat_confirm(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cat_id = int(call.data.split(":")[2])
    await send_or_edit(
        call, "🗑 <b>Удалить категорию и все её товары?</b>",
        reply_markup=kb.confirm_kb("del_cat", cat_id, "adm:cats")
    )


@router.callback_query(F.data.startswith("cfm:del_cat:"))
async def adm_del_cat_exec(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cat_id = int(call.data.split(":")[2])
    await db.delete_category(cat_id)
    await call.answer("✅ Удалено")
    cats = await db.get_categories(active_only=False)
    await send_or_edit(call, "📁 <b>Категории</b>", reply_markup=kb.admin_cats_kb(cats))


# Редактирование категории
@router.callback_query(F.data.startswith("adm:edit_cat:"))
async def adm_edit_cat(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    _, _, field, cat_id = call.data.split(":")
    cat_id = int(cat_id)
    await state.set_state(EditCategory.value)
    await state.update_data(field=field, cat_id=cat_id)

    prompts = {
        "name": "Введите новое название:",
        "emoji": "Отправьте новый эмодзи:",
        "desc": "Введите новое описание:",
        "image": "Отправьте новую картинку (фото):"
    }
    await send_or_edit(call, f"✏️ {prompts[field]}", reply_markup=kb.cancel_kb(f"adm:cat:{cat_id}"))


@router.message(EditCategory.value)
async def adm_edit_cat_save(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await state.clear()
    field, cat_id = data["field"], data["cat_id"]

    db_field = {"name": "name", "emoji": "emoji", "desc": "description", "image": "image_id"}[field]

    if field == "image":
        if not message.photo:
            await message.answer("❌ Отправьте фото")
            return
        value = message.photo[-1].file_id
    else:
        value = message.text

    await db.update_category(cat_id, **{db_field: value})
    await message.answer("✅ Обновлено!", reply_markup=kb.admin_cat_detail_kb(cat_id, True))


# ============ ТОВАРЫ ============
@router.callback_query(F.data == "adm:products")
async def adm_products(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cats = await db.get_categories(active_only=False)
    if not cats:
        await call.answer("Сначала создайте категорию!", show_alert=True)
        return
    await send_or_edit(
        call, "📦 <b>Выберите категорию:</b>",
        reply_markup=kb.admin_products_select_cat_kb(cats)
    )


@router.callback_query(F.data.startswith("adm:cat_prods:"))
async def adm_cat_prods(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    cat_id = int(call.data.split(":")[2])
    prods = await db.get_products(cat_id, active_only=False)
    for p in prods:
        p["stock"] = await db.get_available_items_count(p["id"])
    cat = await db.get_category(cat_id)

    await send_or_edit(
        call, f"📦 <b>Товары в {cat['emoji']} {cat['name']}</b>",
        reply_markup=kb.admin_prods_in_cat_kb(prods, cat_id)
    )


@router.callback_query(F.data.startswith("adm:add_prod:"))
async def adm_add_prod(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    cat_id = int(call.data.split(":")[2])
    await state.set_state(AddProduct.name)
    await state.update_data(category_id=cat_id)
    await send_or_edit(call, "📦 Введите <b>название</b> товара:", reply_markup=kb.cancel_kb())


@router.message(AddProduct.name)
async def ap_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(name=message.text)
    await state.set_state(AddProduct.description)
    await message.answer("📝 Введите <b>описание</b>:", reply_markup=kb.cancel_kb())


@router.message(AddProduct.description)
async def ap_desc(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(description=message.text)
    await state.set_state(AddProduct.price)
    await message.answer("💰 Введите <b>цену</b> в $ (например: 5.99):", reply_markup=kb.cancel_kb())


@router.message(AddProduct.price)
async def ap_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        price = float(message.text.replace(",", "."))
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Неверная цена. Введите число > 0:")
        return

    await state.update_data(price=price)
    await state.set_state(AddProduct.image)
    await message.answer("🖼 Отправьте <b>картинку</b> товара (или /skip):", reply_markup=kb.cancel_kb())


@router.message(AddProduct.image, F.photo)
async def ap_image_photo(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await _finalize_product(message, state, message.photo[-1].file_id)


@router.message(AddProduct.image)
async def ap_image_skip(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text == "/skip":
        await _finalize_product(message, state, None)
    else:
        await message.answer("❌ Отправьте фото или /skip")


async def _finalize_product(message, state, image_id):
    data = await state.get_data()
    await state.clear()
    pid = await db.add_product(data["category_id"], data["name"], data["description"], data["price"], image_id)
    prod = await db.get_product(pid)
    await message.answer(
        f"✅ Товар <b>{data['name']}</b> создан! ({data['price']}$)",
        reply_markup=kb.admin_prod_detail_kb(pid, prod["category_id"], True)
    )


@router.callback_query(F.data.startswith("adm:prod:"))
async def adm_prod_detail(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    pid = int(call.data.split(":")[2])
    prod = await db.get_product(pid)
    if not prod:
        await call.answer("Не найдено", show_alert=True)
        return
    stock = await db.get_available_items_count(pid)

    text = (
        f"📦 <b>{prod['name']}</b>\n\n"
        f"📝 {prod['description']}\n"
        f"💰 Цена: {prod['price']}$\n"
        f"🗃 В наличии: {stock} шт.\n"
        f"👁 Активен: {'Да' if prod['is_active'] else 'Нет'}"
    )
    await send_or_edit(
        call, text,
        reply_markup=kb.admin_prod_detail_kb(pid, prod["category_id"], bool(prod["is_active"])),
        image_id=prod.get("image_id")
    )


@router.callback_query(F.data.startswith("adm:toggle_prod:"))
async def adm_toggle_prod(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    pid = int(call.data.split(":")[2])
    prod = await db.get_product(pid)
    await db.update_product(pid, is_active=0 if prod["is_active"] else 1)
    await call.answer("✅ Готово")
    await adm_prod_detail(call)


@router.callback_query(F.data.startswith("adm:del_prod:"))
async def adm_del_prod_confirm(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    pid = int(call.data.split(":")[2])
    prod = await db.get_product(pid)
    await send_or_edit(
        call, "🗑 <b>Удалить товар?</b>",
        reply_markup=kb.confirm_kb("del_prod", pid, f"adm:cat_prods:{prod['category_id']}")
    )


@router.callback_query(F.data.startswith("cfm:del_prod:"))
async def adm_del_prod_exec(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    pid = int(call.data.split(":")[2])
    prod = await db.get_product(pid)
    cat_id = prod["category_id"]
    await db.delete_product(pid)
    await call.answer("✅ Удалено")
    prods = await db.get_products(cat_id, active_only=False)
    for p in prods:
        p["stock"] = await db.get_available_items_count(p["id"])
    await send_or_edit(call, "📦 <b>Товары</b>", reply_markup=kb.admin_prods_in_cat_kb(prods, cat_id))


# Редактирование товара
@router.callback_query(F.data.startswith("adm:edit_prod:"))
async def adm_edit_prod(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    _, _, field, pid = call.data.split(":")
    pid = int(pid)
    await state.set_state(EditProduct.value)
    await state.update_data(field=field, pid=pid)

    prompts = {
        "name": "Введите новое название:",
        "price": "Введите новую цену:",
        "desc": "Введите новое описание:",
        "image": "Отправьте новую картинку:"
    }
    await send_or_edit(call, f"✏️ {prompts[field]}", reply_markup=kb.cancel_kb(f"adm:prod:{pid}"))


@router.message(EditProduct.value)
async def adm_edit_prod_save(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    field, pid = data["field"], data["pid"]

    db_field = {"name": "name", "price": "price", "desc": "description", "image": "image_id"}[field]

    if field == "image":
        if not message.photo:
            await message.answer("❌ Отправьте фото")
            return
        value = message.photo[-1].file_id
    elif field == "price":
        try:
            value = float(message.text.replace(",", "."))
        except ValueError:
            await message.answer("❌ Неверная цена")
            return
    else:
        value = message.text

    await state.clear()
    await db.update_product(pid, **{db_field: value})
    prod = await db.get_product(pid)
    await message.answer("✅ Обновлено!", reply_markup=kb.admin_prod_detail_kb(pid, prod["category_id"], bool(prod["is_active"])))


# Загрузка позиций
@router.callback_query(F.data.startswith("adm:upload:"))
async def adm_upload(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    pid = int(call.data.split(":")[2])
    await state.set_state(UploadItems.items)
    await state.update_data(product_id=pid)
    await send_or_edit(
        call,
        "📝 <b>Загрузка позиций</b>\n\n"
        "Отправьте позиции (каждая с новой строки) или файл .txt:\n\n"
        "<i>Пример:\nlogin1:pass1\nlogin2:pass2</i>",
        reply_markup=kb.cancel_kb(f"adm:prod:{pid}")
    )


@router.message(UploadItems.items)
async def adm_upload_process(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    pid = data["product_id"]

    items = []
    if message.document:
        try:
            file = await bot.get_file(message.document.file_id)
            content = await bot.download_file(file.file_path)
            text = content.read().decode("utf-8", errors="ignore")
            items = [l.strip() for l in text.split("\n") if l.strip()]
        except Exception as e:
            await message.answer(f"❌ Ошибка чтения файла: {e}")
            return
    elif message.text:
        items = [l.strip() for l in message.text.split("\n") if l.strip()]

    if not items:
        await message.answer("❌ Нет позиций для загрузки")
        return

    await state.clear()
    await db.add_items(pid, items)
    stock = await db.get_available_items_count(pid)
    await message.answer(
        f"✅ Загружено <b>{len(items)}</b> позиций!\n🗃 Всего: {stock}",
        reply_markup=kb.admin_menu_kb()
    )


# ============ ОФОРМЛЕНИЕ ============
@router.callback_query(F.data == "adm:design")
async def adm_design(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await send_or_edit(
        call,
        "🎨 <b>Оформление бота</b>\n\n"
        "Настройте тексты и изображения для разделов бота.\n"
        "В текстах можно использовать <code>{name}</code> — имя пользователя.",
        reply_markup=kb.admin_design_kb()
    )


@router.callback_query(F.data.startswith("adm:txt:"))
async def adm_edit_text(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    key = call.data.split(":")[2]
    current = await db.get_setting(key)
    await state.set_state(EditText.value)
    await state.update_data(key=key)

    await send_or_edit(
        call,
        f"✏️ <b>Редактирование текста</b>\n\n"
        f"<b>Текущий:</b>\n<code>{current[:500]}</code>\n\n"
        f"Отправьте новый текст (поддерживается HTML):",
        reply_markup=kb.cancel_kb("adm:design")
    )


@router.message(EditText.value)
async def adm_save_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await state.clear()
    await db.set_setting(data["key"], message.html_text)
    await message.answer("✅ Текст обновлён!", reply_markup=kb.admin_menu_kb())


@router.callback_query(F.data.startswith("adm:img:"))
async def adm_edit_img(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    key = call.data.split(":")[2]
    await state.set_state(EditImage.value)
    await state.update_data(key=key)
    await send_or_edit(
        call,
        "🖼 Отправьте фото для этого раздела.\n\n"
        "Отправьте /delete чтобы удалить фото.",
        reply_markup=kb.cancel_kb("adm:design")
    )


@router.message(EditImage.value, F.photo)
async def adm_save_img(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await state.clear()
    await db.set_setting(data["key"], message.photo[-1].file_id)
    await message.answer("✅ Фото обновлено!", reply_markup=kb.admin_menu_kb())


@router.message(EditImage.value)
async def adm_delete_img(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text == "/delete":
        data = await state.get_data()
        await state.clear()
        await db.set_setting(data["key"], "")
        await message.answer("✅ Фото удалено!", reply_markup=kb.admin_menu_kb())
    else:
        await message.answer("❌ Отправьте фото или /delete")


# ============ ВЫВОДЫ ============
@router.callback_query(F.data == "adm:withdraws")
async def adm_withdraws(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    wds = await db.get_pending_withdrawals()
    if not wds:
        await send_or_edit(
            call, "💸 <b>Заявки на вывод</b>\n\nНет новых заявок",
            reply_markup=kb.back_only_kb("admin_panel")
        )
        return
    await send_or_edit(
        call, f"💸 <b>Заявки на вывод</b> ({len(wds)})",
        reply_markup=kb.admin_withdraws_kb(wds)
    )


@router.callback_query(F.data.startswith("adm:w:"))
async def adm_w_detail(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    wid = int(call.data.split(":")[2])
    w = await db.get_withdrawal(wid)
    if not w:
        await call.answer("Не найдено", show_alert=True)
        return

    user = await db.get_user(w["user_id"])
    method_name = "CryptoBot" if w["method"] == "crypto_bot" else "xRocket"

    text = (
        f"💸 <b>Заявка #{w['id']}</b>\n\n"
        f"👤 Пользователь: {user['first_name']} (<code>{user['user_id']}</code>)\n"
        f"💰 Сумма: <b>{w['amount']}$</b>\n"
        f"💳 Метод: <b>{method_name}</b>\n"
        f"📩 Адрес: <code>{w['address']}</code>\n"
        f"📅 Дата: {w['created_at']}"
    )
    await send_or_edit(call, text, reply_markup=kb.admin_withdraw_detail_kb(wid))


@router.callback_query(F.data.startswith("adm:w_ok:"))
async def adm_w_ok(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    wid = int(call.data.split(":")[2])
    w = await db.get_withdrawal(wid)
    await db.update_withdrawal(wid, "completed", "Выплачено")

    try:
        await call.bot.send_message(
            w["user_id"],
            f"✅ <b>Заявка #{wid} выполнена!</b>\n\n"
            f"💰 Сумма: {w['amount']}$\n"
            f"📩 На адрес: {w['address']}"
        )
    except Exception:
        pass

    await call.answer("✅ Отмечено как выплачено")
    await adm_withdraws(call)


@router.callback_query(F.data.startswith("adm:w_no:"))
async def adm_w_no(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    wid = int(call.data.split(":")[2])
    w = await db.get_withdrawal(wid)

    # Возвращаем деньги на баланс
    await db.add_ref_balance(w["user_id"], w["amount"])
    await db.update_withdrawal(wid, "rejected", "Отклонено админом")

    try:
        await call.bot.send_message(
            w["user_id"],
            f"❌ <b>Заявка #{wid} отклонена</b>\n\n"
            f"Средства ({w['amount']}$) возвращены на баланс."
        )
    except Exception:
        pass

    await call.answer("❌ Отклонено, средства возвращены")
    await adm_withdraws(call)


# ============ ПОЛЬЗОВАТЕЛИ ============
@router.callback_query(F.data == "adm:users")
async def adm_users(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    count = await db.get_user_count()
    await send_or_edit(
        call, f"👥 <b>Пользователи</b>\n\nВсего: {count}",
        reply_markup=kb.admin_users_kb()
    )


@router.callback_query(F.data == "adm:find_user")
async def adm_find_user(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(UserManage.user_id)
    await send_or_edit(
        call, "🔍 Отправьте ID пользователя:",
        reply_markup=kb.cancel_kb("adm:users")
    )


@router.message(UserManage.user_id)
async def adm_find_user_result(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int(message.text)
    except ValueError:
        await message.answer("❌ Неверный ID")
        return

    await state.clear()
    user = await db.get_user(uid)
    if not user:
        await message.answer("❌ Пользователь не найден", reply_markup=kb.admin_menu_kb())
        return

    await show_user_info(message, user)


async def show_user_info(event, user):
    orders = await db.get_user_orders(user["user_id"], limit=5)
    refs = await db.get_user_referrals(user["user_id"])

    text = (
        f"👤 <b>Пользователь #{user['user_id']}</b>\n\n"
        f"Имя: {user['first_name']}\n"
        f"Username: @{user['username'] or '—'}\n"
        f"Баланс реф.: <b>{user['ref_balance']:.2f}$</b>\n"
        f"Потрачено: {user['total_spent']:.2f}$\n"
        f"Заработано: {user['total_earned']:.2f}$\n"
        f"Покупок: {len(orders)}\n"
        f"Рефералов: {len(refs)}\n"
        f"Статус: {'🚫 Забанен' if user['is_banned'] else '✅ Активен'}\n"
        f"Регистрация: {user['created_at'][:10]}"
    )

    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb.admin_user_detail_kb(user["user_id"], bool(user["is_banned"])))
    else:
        await send_or_edit(event, text, reply_markup=kb.admin_user_detail_kb(user["user_id"], bool(user["is_banned"])))


@router.callback_query(F.data.startswith("adm:u_ban:"))
async def adm_u_ban(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    uid = int(call.data.split(":")[2])
    user = await db.get_user(uid)
    if user["is_banned"]:
        await db.unban_user(uid)
        await call.answer("✅ Разбанен")
    else:
        await db.ban_user(uid)
        await call.answer("🚫 Забанен")
    user = await db.get_user(uid)
    await show_user_info(call, user)


@router.callback_query(F.data.startswith("adm:u_add:"))
async def adm_u_add(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    uid = int(call.data.split(":")[2])
    await state.set_state(UserManage.amount)
    await state.update_data(uid=uid, action="add")
    await send_or_edit(call, "💰 Введите сумму для начисления:", reply_markup=kb.cancel_kb("adm:users"))


@router.callback_query(F.data.startswith("adm:u_sub:"))
async def adm_u_sub(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    uid = int(call.data.split(":")[2])
    await state.set_state(UserManage.amount)
    await state.update_data(uid=uid, action="sub")
    await send_or_edit(call, "➖ Введите сумму для списания:", reply_markup=kb.cancel_kb("adm:users"))


@router.message(UserManage.amount)
async def adm_u_amount(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("❌ Неверная сумма")
        return

    data = await state.get_data()
    await state.clear()
    uid, action = data["uid"], data["action"]

    if action == "add":
        await db.add_balance(uid, amount)
        await message.answer(f"✅ Начислено {amount}$ пользователю {uid}", reply_markup=kb.admin_menu_kb())
    else:
        await db.subtract_ref_balance(uid, amount)
        await message.answer(f"✅ Списано {amount}$ с пользователя {uid}", reply_markup=kb.admin_menu_kb())


# ============ РАССЫЛКА ============
@router.callback_query(F.data == "adm:broadcast")
async def adm_bc(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(Broadcast.message)
    await send_or_edit(
        call,
        "📢 <b>Рассылка</b>\n\n"
        "Отправьте сообщение для рассылки (текст, фото, видео):",
        reply_markup=kb.cancel_kb()
    )


@router.message(Broadcast.message)
async def adm_bc_preview(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.update_data(
        chat_id=message.chat.id,
        message_id=message.message_id
    )
    await state.set_state(Broadcast.confirm)

    await message.answer(
        "👆 Так будет выглядеть сообщение.\n\nПодтверждаете рассылку?",
        reply_markup=kb.broadcast_confirm_kb()
    )


@router.callback_query(F.data == "bc_send", Broadcast.confirm)
async def adm_bc_send(call: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(call.from_user.id):
        return

    data = await state.get_data()
    await state.clear()

    users = await db.get_all_users()
    sent, failed = 0, 0

    await call.message.edit_text(f"📢 Рассылка... 0/{len(users)}")

    for i, user in enumerate(users):
        try:
            await bot.copy_message(
                chat_id=user["user_id"],
                from_chat_id=data["chat_id"],
                message_id=data["message_id"]
            )
            sent += 1
        except Exception:
            failed += 1

        if (i + 1) % 25 == 0:
            try:
                await call.message.edit_text(f"📢 Рассылка... {i+1}/{len(users)}")
            except Exception:
                pass
        await asyncio.sleep(0.05)  # Антиспам

    await call.message.edit_text(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"📨 Отправлено: {sent}\n"
        f"❌ Не доставлено: {failed}",
        reply_markup=kb.admin_menu_kb()
    )

# MANUAL_TOPUPS_ADMIN
@router.callback_query(F.data == "adm:topups")
async def adm_manual_topups(call):
    if not is_admin(call.from_user.id):
        return
    items = await db.get_pending_manual_topups()
    if not items:
        await send_or_edit(call, "💳 <b>Ручные пополнения / оплаты</b>\n\nНет заявок", reply_markup=kb.back_only_kb("admin_panel"))
        return
    await send_or_edit(call, f"💳 <b>Ручные заявки</b> ({len(items)})", reply_markup=kb.admin_manual_topups_kb(items))
@router.callback_query(F.data.startswith("adm:top:"))
async def adm_manual_detail(call):
    if not is_admin(call.from_user.id):
        return
    mid = int(call.data.split(":")[2])
    m = await db.get_manual_topup(mid)
    if not m:
        await call.answer("Не найдено", show_alert=True)
        return
    u = await db.get_user(m["user_id"])
    prod = await db.get_product(int(m.get("product_id") or 0)) if int(m.get("product_id") or 0) else None
    kind = f"📦 Товар: {prod['name']}" if prod else "💰 Пополнение баланса"
    await send_or_edit(call, f"💳 <b>Заявка #{m['id']}</b>\n{kind}\n👤 {u['first_name'] if u else '?'} (<code>{m['user_id']}</code>)\n💵 <b>{m['amount']}$</b> USDT TRC20\n🧾 <code>{m.get('tx_hash') or '-'}</code>\n📅 {m['created_at']}", reply_markup=kb.admin_manual_topup_detail_kb(mid), image_id=m.get("photo_id") or None)
@router.callback_query(F.data.startswith("adm:top_ok:"))
async def adm_manual_ok(call):
    if not is_admin(call.from_user.id):
        return
    mid = int(call.data.split(":")[2])
    m = await db.get_manual_topup(mid)
    if not m or m["status"] != "pending":
        await call.answer("Уже обработано", show_alert=True)
        return
    await db.update_manual_topup(mid, "approved")
    pid = int(m.get("product_id") or 0)
    amount = float(m["amount"])
    if pid:
        prod = await db.get_product(pid)
        bought = await db.buy_item(pid, m["user_id"])
        if not bought:
            await db.add_balance(m["user_id"], amount)
            try:
                await call.bot.send_message(m["user_id"], f"⚠️ <b>Оплата #{mid} одобрена</b>, но товар закончился.\n💵 {amount}$ зачислены на баланс.")
            except Exception:
                pass
        else:
            item_id, content = bought
            oid = await db.create_order(m["user_id"], pid, amount, "manual_usdt", f"manual:{mid}")
            await db.complete_order(oid, item_id)
            buyer = await db.get_user(m["user_id"])
            if buyer and buyer.get("referrer_id") and prod:
                from config import REFERRAL_PERCENT as RP
                ref_amt = round(float(prod["price"]) * RP / 100, 4)
                if ref_amt > 0:
                    await db.add_ref_balance(buyer["referrer_id"], ref_amt)
                    try:
                        await call.bot.send_message(buyer["referrer_id"], f"💰 +{ref_amt:.4f}$ от покупки реферала!")
                    except Exception:
                        pass
            try:
                await call.bot.send_message(m["user_id"], f"✅ <b>Оплата USDT TRC20 одобрена!</b>\n\n📦 {prod['name'] if prod else 'Товар'}\n\n📄 <b>Ваш товар:</b>\n<code>{content}</code>\n\n⚠️ Сохраните данные!")
            except Exception:
                pass
    else:
        await db.add_balance(m["user_id"], amount)
        try:
            await call.bot.send_message(m["user_id"], f"✅ <b>Баланс пополнен!</b>\n💵 +{amount}$ USDT TRC20")
        except Exception:
            pass
    await call.answer("✅ Одобрено")
    await adm_manual_topups(call)
@router.callback_query(F.data.startswith("adm:top_no:"))
async def adm_manual_no(call):
    if not is_admin(call.from_user.id):
        return
    mid = int(call.data.split(":")[2])
    m = await db.get_manual_topup(mid)
    if not m or m["status"] != "pending":
        await call.answer("Уже обработано", show_alert=True)
        return
    await db.update_manual_topup(mid, "rejected")
    try:
        await call.bot.send_message(m["user_id"], f"❌ <b>Заявка #{mid} отклонена</b>\nПроверьте TxID/скриншот или напишите в поддержку.")
    except Exception:
        pass
    await call.answer("❌ Отклонено")
    await adm_manual_topups(call)

# BUTTON_CUSTOM_ADMIN
from states import EditButton
_BTN_NAMES = {"catalog": "Каталог", "profile": "Профиль", "referral": "Рефералка", "faq": "FAQ", "support": "Поддержка", "buy": "Купить товар", "pay_crypto": "Оплата CryptoBot", "pay_xrocket": "Оплата xRocket", "pay_balance": "Оплата с баланса", "pay_manual": "Оплата USDT TRC20"}
_BTN_KEYS = {"catalog": "btn_catalog", "profile": "btn_profile", "referral": "btn_referral", "faq": "btn_faq", "support": "btn_support", "buy": "btn_buy", "pay_crypto": "btn_pay_crypto", "pay_xrocket": "btn_pay_xrocket", "pay_balance": "btn_pay_balance", "pay_manual": "btn_pay_manual"}
@router.callback_query(F.data == "adm:buttons")
async def adm_buttons(call):
    if not is_admin(call.from_user.id):
        return
    await send_or_edit(call, "🎛 <b>Кнопки</b>\n\nВыбери кнопку: меняется текст, Premium emoji-иконка и цвет (новый Bot API).", reply_markup=kb.admin_buttons_kb())
@router.callback_query(F.data.startswith("adm:btn:"))
async def adm_btn_detail(call):
    if not is_admin(call.from_user.id):
        return
    name = call.data.split(":")[2]
    text = await db.get_setting(_BTN_KEYS.get(name, "btn_catalog"))
    icon = await db.get_setting("icon_btn_" + name)
    style = await db.get_setting("style_btn_" + name) or "обычный"
    await send_or_edit(call, f"🎛 <b>{_BTN_NAMES.get(name, name)}</b>\n\n📝 Текст: {text or 'по умолчанию'}\n✨ Premium icon ID: <code>{icon or 'нет'}</code>\n🎨 Цвет: <b>{style}</b>", reply_markup=kb.admin_button_detail_kb(name))
@router.callback_query(F.data.startswith("adm:btnicon:"))
async def adm_btn_icon(call, state):
    if not is_admin(call.from_user.id):
        return
    name = call.data.split(":")[2]
    await state.set_state(EditButton.icon)
    await state.update_data(btn=name)
    await send_or_edit(call, "✨ Пришли <b>один Premium emoji</b> одним сообщением — бот возьмёт его custom_emoji_id как иконку кнопки.\n\n/delete — убрать иконку.", reply_markup=kb.cancel_kb(f"adm:btn:{name}"))
@router.message(EditButton.icon)
async def adm_btn_icon_save(message, state):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    name = data.get("btn", "catalog")
    if message.text == "/delete":
        await state.clear()
        await db.set_setting("icon_btn_" + name, "")
        await message.answer("✅ Premium-иконка удалена", reply_markup=kb.admin_button_detail_kb(name))
        return
    eid = None
    for e in (message.entities or []):
        if getattr(e, "custom_emoji_id", None):
            eid = e.custom_emoji_id
            break
    if not eid:
        await message.answer("❌ Это не Premium emoji. Пришли именно Premium emoji одним сообщением или /delete")
        return
    await state.clear()
    await db.set_setting("icon_btn_" + name, str(eid))
    await message.answer("✅ Premium-иконка сохранена! Кнопка обновится в меню.", reply_markup=kb.admin_menu_kb())
@router.callback_query(F.data.startswith("adm:btnstyle:"))
async def adm_btn_style(call):
    if not is_admin(call.from_user.id):
        return
    name = call.data.split(":")[2]
    await send_or_edit(call, "🎨 Выбери цвет кнопки (Bot API style):", reply_markup=kb.admin_button_style_kb(name))
@router.callback_query(F.data.startswith("adm:setstyle:"))
async def adm_set_style(call):
    if not is_admin(call.from_user.id):
        return
    p = call.data.split(":")
    name, style = p[2], p[3]
    await db.set_setting("style_btn_" + name, style)
    await call.answer("✅ Цвет сохранён")
    call = call.model_copy(update={"data": f"adm:btn:{name}"})
    await adm_btn_detail(call)

# SUBSCRIPTION_ADMIN
from states import AddSubChannel, SubInvite
@router.callback_query(F.data == "adm:subs")
async def adm_subs(call):
    if not is_admin(call.from_user.id):
        return
    channels = await db.get_sub_channels()
    enabled = await db.get_setting_bool("subs_enabled")
    await send_or_edit(call, f"📢 <b>Обязательная подписка</b>\n\nСтатус: <b>{'🟢 ВКЛ' if enabled else '🔴 ВЫКЛ'}</b>\nКаналов: <b>{len(channels)}</b>\n\nПроверка работает, если включено И есть активные каналы.", reply_markup=kb.admin_subs_kb(channels, enabled))
@router.callback_query(F.data == "adm:sub_toggle")
async def adm_sub_toggle(call):
    if not is_admin(call.from_user.id):
        return
    enabled = await db.get_setting_bool("subs_enabled")
    await db.set_setting("subs_enabled", "0" if enabled else "1")
    try:
        from middlewares.subscription import _CACHE
        _CACHE.clear()
    except Exception:
        pass
    await call.answer("✅ Переключено")
    await adm_subs(call)
@router.callback_query(F.data == "adm:sub_add")
async def adm_sub_add(call, state):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AddSubChannel.data)
    await send_or_edit(call, "➕ <b>Добавление канала</b>\n\nСделай бота админом канала и затем:\n\n• Перешли сюда любой пост из канала, ИЛИ\n• Отправь <code>@username</code> канала, ИЛИ\n• Отправь chat_id вида <code>-100...</code>\n\nДля приватного канала после добавления можно задать invite-ссылку.", reply_markup=kb.cancel_kb("adm:subs"))
@router.message(AddSubChannel.data)
async def adm_sub_add_save(message, state):
    if not is_admin(message.from_user.id):
        return
    chat_id = None
    username = None
    title = None
    invite = None
    fwd = getattr(message, "forward_from_chat", None)
    if fwd:
        chat_id = fwd.id
        username = getattr(fwd, "username", None)
        title = getattr(fwd, "title", None)
    else:
        text = (message.text or "").strip()
        if not text:
            await message.answer("❌ Пришли @username, chat_id или перешли пост")
            return
        try:
            chat = await message.bot.get_chat(text)
            chat_id = chat.id
            username = getattr(chat, "username", None)
            title = getattr(chat, "title", None)
            try:
                invite = getattr(chat, "invite_link", None)
            except Exception:
                invite = None
        except Exception as e:
            await message.answer(f"❌ Не удалось найти канал: <code>{str(e)[:150]}</code>\nСделай бота админом канала и повтори.")
            return
    try:
        me = await message.bot.get_me()
        mem = await message.bot.get_chat_member(chat_id=chat_id, user_id=me.id)
        if str(getattr(mem, "status", "")) not in ("ChatMemberStatus.ADMINISTRATOR", "ChatMemberStatus.CREATOR", "administrator", "creator"):
            await message.answer("⚠️ Бот не админ в этом канале — проверка подписки может не работать. Добавил, но сделай его админом.")
    except Exception:
        pass
    if not invite and not username:
        try:
            invite = await message.bot.export_chat_invite_link(chat_id)
        except Exception:
            invite = None
    cid = await db.add_sub_channel(chat_id, username, title, invite)
    await state.clear()
    try:
        from middlewares.subscription import _CACHE
        _CACHE.clear()
    except Exception:
        pass
    await message.answer(f"✅ Канал добавлен!\n🆔 <code>{chat_id}</code>\n📛 {title or username or '-'}\n🔗 {invite or ('@' + username if username else '-')}", reply_markup=kb.admin_menu_kb())
@router.callback_query(F.data.startswith("adm:sub:"))
async def adm_sub_detail(call):
    if not is_admin(call.from_user.id):
        return
    cid = int(call.data.split(":")[2])
    ch = await db.get_sub_channel(cid)
    if not ch:
        await call.answer("Не найдено", show_alert=True)
        return
    await send_or_edit(call, f"📢 <b>Канал #{ch['id']}</b>\n\n📛 {ch.get('title') or '-'}\n🆔 <code>{ch['chat_id']}</code>\n@ {ch.get('username') or '-'}\n🔗 {ch.get('invite_link') or '-'}\n📊 {'🟢 активен' if ch['is_active'] else '🔴 скрыт'}", reply_markup=kb.admin_sub_detail_kb(cid, ch['is_active']))
@router.callback_query(F.data.startswith("adm:sub_tog:"))
async def adm_sub_tog(call):
    if not is_admin(call.from_user.id):
        return
    cid = int(call.data.split(":")[2])
    await db.toggle_sub_channel(cid)
    try:
        from middlewares.subscription import _CACHE
        _CACHE.clear()
    except Exception:
        pass
    await call.answer("✅ Переключено")
    call = call.model_copy(update={"data": f"adm:sub:{cid}"})
    await adm_sub_detail(call)
@router.callback_query(F.data.startswith("adm:sub_del:"))
async def adm_sub_del(call):
    if not is_admin(call.from_user.id):
        return
    cid = int(call.data.split(":")[2])
    await db.delete_sub_channel(cid)
    try:
        from middlewares.subscription import _CACHE
        _CACHE.clear()
    except Exception:
        pass
    await call.answer("🗑 Удалено")
    await adm_subs(call)
@router.callback_query(F.data.startswith("adm:sub_link:"))
async def adm_sub_link(call, state):
    if not is_admin(call.from_user.id):
        return
    cid = int(call.data.split(":")[2])
    await state.set_state(SubInvite.link)
    await state.update_data(cid=cid)
    await send_or_edit(call, "🔗 Пришли новую invite-ссылку (https://t.me/+...) или /auto чтобы бот сгенерировал её сам (нужны права 'Пригласительные ссылки').", reply_markup=kb.cancel_kb(f"adm:sub:{cid}"))
@router.message(SubInvite.link)
async def adm_sub_link_save(message, state):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    cid = int(data.get("cid", 0))
    ch = await db.get_sub_channel(cid)
    if not ch:
        await state.clear()
        await message.answer("❌ Канал не найден")
        return
    link = (message.text or "").strip()
    if link == "/auto":
        try:
            link = await message.bot.export_chat_invite_link(ch["chat_id"])
        except Exception as e:
            await state.clear()
            await message.answer(f"❌ Не получилось: <code>{str(e)[:150]}</code>")
            return
    if not link.startswith("http"):
        await message.answer("❌ Пришли ссылку https://t.me/... или /auto")
        return
    await db.update_sub_invite(cid, link)
    await state.clear()
    await message.answer("✅ Ссылка обновлена", reply_markup=kb.admin_menu_kb())
