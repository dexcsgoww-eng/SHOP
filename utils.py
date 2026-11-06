from aiogram.types import CallbackQuery, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest
async def send_or_edit(event, text, reply_markup=None, image_id=None):
    is_cb = isinstance(event, CallbackQuery)
    message = event.message if is_cb else event
    if not image_id or not str(image_id).strip():
        image_id = None
    try:
        if image_id:
            if is_cb and message.photo:
                await message.edit_media(media=InputMediaPhoto(media=image_id, caption=text), reply_markup=reply_markup)
            elif is_cb:
                try:
                    await message.delete()
                except Exception:
                    pass
                await message.answer_photo(photo=image_id, caption=text, reply_markup=reply_markup)
            else:
                await message.answer_photo(photo=image_id, caption=text, reply_markup=reply_markup)
        else:
            if is_cb and message.photo:
                try:
                    await message.delete()
                except Exception:
                    pass
                await message.answer(text, reply_markup=reply_markup)
            elif is_cb:
                await message.edit_text(text, reply_markup=reply_markup)
            else:
                await message.answer(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            if is_cb:
                await event.answer()
            return
        try:
            if image_id:
                await message.answer_photo(photo=image_id, caption=text, reply_markup=reply_markup)
            else:
                await message.answer(text, reply_markup=reply_markup)
        except Exception:
            pass
