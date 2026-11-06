import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from config import BOT_TOKEN, PROXY_URL
import database as db
import db_ext
import xrocket_pay
from handlers import user, payment, referral, admin, subscription, chat_member, admin_ext
from handlers import promocodes, section_buttons

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)


async def main():
    await db.init_db()
    await db_ext.ensure_schema()
    await xrocket_pay.init_db()

    try:
        import aiogram
        from keyboards import _HAS_STYLE_ICON
        logger.info(f"aiogram={aiogram.__version__} | style/icon: {'OK' if _HAS_STYLE_ICON else 'NO'}")
    except Exception:
        pass

    session = None
    if PROXY_URL and "://" in PROXY_URL:
        logger.info(f"Proxy: {PROXY_URL}")
        try:
            session = AiohttpSession(proxy=PROXY_URL)
        except Exception as e:
            logger.warning(f"Proxy err: {e}")

    bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    try:
        from middlewares.subscription import SubscriptionMiddleware, watcher_loop
        dp.message.middleware(SubscriptionMiddleware())
        dp.callback_query.middleware(SubscriptionMiddleware())
        asyncio.create_task(watcher_loop())
        logger.info("Subs middleware ON")
    except Exception as e:
        logger.warning(f"Subs err: {e}")

    # Порядок важен! Новые роутеры ДО admin
    dp.include_router(xrocket_pay.router)
    dp.include_router(subscription.router)
    dp.include_router(chat_member.router)
    dp.include_router(admin_ext.router)
    dp.include_router(promocodes.router)
    dp.include_router(section_buttons.router)
    dp.include_router(user.router)
    dp.include_router(payment.router)
    dp.include_router(referral.router)
    dp.include_router(admin.router)

    me = await bot.get_me()
    logger.info(f"Bot @{me.username} started")
    await bot.delete_webhook(drop_pending_updates=True)
    await xrocket_pay.resume(bot)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "chat_member", "my_chat_member"])


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped")