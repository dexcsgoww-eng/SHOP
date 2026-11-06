import sys, logging, asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from config import BOT_TOKEN, PROXY_URL
import database as db
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("bot.log", encoding="utf-8")])
logger = logging.getLogger(__name__)
async def main():
    logger.info("🚀 Запуск бота...")
    await db.init_db()
    logger.info("✅ База данных готова")
    session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else None
    if PROXY_URL:
        logger.info(f"🌐 Прокси Telegram: {PROXY_URL}")
    bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    # --- subscription middleware ---
    try:
        from middlewares.subscription import SubscriptionMiddleware as _SubMW
        dp.message.middleware(_SubMW())
        dp.callback_query.middleware(_SubMW())
    except Exception as _e:
        print('subs middleware err:', _e)

except Exception as _e:
    print('subs import err:', _e)

    from handlers import user, payment, referral, admin, subscription
    dp.include_router(user.router)
    dp.include_router(subscription.router)
    dp.include_router(payment.router)
    dp.include_router(referral.router)
    dp.include_router(admin.router)
    me = await bot.get_me()
    logger.info(f"✅ Бот запущен: @{me.username}")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)
if __name__ == "__main__":
    asyncio.run(main())
