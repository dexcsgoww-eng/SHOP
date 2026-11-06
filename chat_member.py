import logging
from aiogram import Router
from aiogram.types import ChatMemberUpdated
logger = logging.getLogger(__name__)
router = Router()

@router.chat_member()
async def on_chat_member_update(event: ChatMemberUpdated):
    try:
        from middlewares.subscription import invalidate_user
        uid = event.new_chat_member.user.id if event.new_chat_member else None
        if uid:
            invalidate_user(uid)
    except Exception as e:
        logger.warning(f"chat_member err: {e}")

@router.my_chat_member()
async def on_my_chat_member(event: ChatMemberUpdated):
    pass
