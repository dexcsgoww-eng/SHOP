import time, logging, asyncio
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update, ChatMemberUpdated
import database as db
import keyboards as kb
from config import ADMIN_IDS

logger = logging.getLogger(__name__)
_CACHE = {}
_CACHE_TTL = 15
ALLOWED_CB = {"subs_check"}
_OK_STATUSES = {"member", "administrator", "creator", "owner",
                "ChatMemberStatus.MEMBER", "ChatMemberStatus.ADMINISTRATOR",
                "ChatMemberStatus.CREATOR", "ChatMemberStatus.OWNER"}
_BAD_STATUSES = {"left", "kicked", "restricted",
                 "ChatMemberStatus.LEFT", "ChatMemberStatus.KICKED", "ChatMemberStatus.RESTRICTED"}

async def _is_subscribed(bot, user_id, chat_id):
    try:
        m = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        status = getattr(m, "status", None)
        if status is None:
            return True
        s = str(status)
        if s in _OK_STATUSES:
            if s in ("restricted", "ChatMemberStatus.RESTRICTED"):
                is_member = getattr(m, "is_member", None)
                if is_member is False:
                    return False
            return True
        if s in _BAD_STATUSES:
            if s in ("restricted", "ChatMemberStatus.RESTRICTED"):
                is_member = getattr(m, "is_member", None)
                return bool(is_member)
            return False
        return False
    except Exception as e:
        err = str(e).lower()
        if "chat not found" in err or "bot is not a member" in err or "not enough rights" in err or "forbidden" in err or "chat_admin_required" in err:
            logger.warning(f"Sub check fail chat {chat_id}: {e} — disabling channel")
            try:
                await db.deactivate_sub_channel_by_chat(chat_id)
            except Exception:
                pass
            return True
        if "user not found" in err or "participant_id_invalid" in err:
            return False
        logger.warning(f"Sub check error chat {chat_id} user {user_id}: {e}")
        return True

async def get_unsubscribed(bot, user_id, force=False):
    if user_id in ADMIN_IDS:
        return []
    try:
        if not await db.get_setting_bool("subs_enabled"):
            return []
        channels = await db.get_active_sub_channels()
    except Exception as e:
        logger.warning(f"Sub load err: {e}")
        return []
    if not channels:
        return []
    now = time.time()
    key = (user_id, tuple(c["chat_id"] for c in channels))
    if not force:
        c = _CACHE.get(key)
        if c and c[0] > now:
            return c[1]
    missing = []
    for ch in channels:
        try:
            ok = await _is_subscribed(bot, user_id, int(ch["chat_id"]))
        except Exception:
            ok = True
        if not ok:
            missing.append(ch)
    _CACHE[key] = (now + _CACHE_TTL, missing)
    return missing

def invalidate_user(user_id):
    for k in list(_CACHE.keys()):
        if k[0] == user_id:
            _CACHE.pop(k, None)

def invalidate_all():
    _CACHE.clear()

async def watcher_loop():
    while True:
        try:
            await asyncio.sleep(30)
            now = time.time()
            for k in list(_CACHE.keys()):
                if _CACHE[k][0] <= now:
                    _CACHE.pop(k, None)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Watcher err: {e}")

class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = None
        force = False
        if isinstance(event, (Message, CallbackQuery)):
            user = event.from_user
            if isinstance(event, Message) and event.text and event.text.startswith("/start"):
                force = True
        elif isinstance(event, Update):
            user = (event.message and event.message.from_user) or (event.callback_query and event.callback_query.from_user)
            if event.message and event.message.text and event.message.text.startswith("/start"):
                force = True
        if not user or user.id in ADMIN_IDS:
            return await handler(event, data)
        if isinstance(event, CallbackQuery) and event.data in ALLOWED_CB:
            return await handler(event, data)
        bot = data.get("bot")
        if not bot:
            return await handler(event, data)
        if force:
            invalidate_user(user.id)
        missing = await get_unsubscribed(bot, user.id, force=force)
        if not missing:
            return await handler(event, data)
        text = "📢 <b>Для использования бота подпишитесь на канал(ы):</b>\n\nПосле подписки нажмите «✅ Я подписался — проверить».\n\n⚠️ Если вы покинете канал — доступ снова закроется."
        mk = kb.sub_required_kb(missing)
        try:
            if isinstance(event, CallbackQuery):
                try:
                    await event.message.edit_text(text, reply_markup=mk)
                except Exception:
                    await event.message.answer(text, reply_markup=mk)
                await event.answer()
            elif isinstance(event, Message):
                await event.answer(text, reply_markup=mk)
        except Exception as e:
            logger.warning(f"Sub prompt err: {e}")
        return
