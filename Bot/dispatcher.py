import aiogram
from aiogram.client.default import DefaultBotProperties
from loguru import logger

import config

dp = aiogram.Dispatcher()
bot = aiogram.Bot(
    token=config.TOKEN,
    default=DefaultBotProperties(parse_mode="HTML", link_preview_is_disabled=True),
)


@dp.shutdown()
async def on_shutdown():
    logger.info("Bot is shutting down...")
    await bot.session.close()
