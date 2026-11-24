"""Telegram Bot entrypoint (aiogram 3)."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app.config import TELEGRAM_BOT_TOKEN
from bot.handlers import WhitelistMiddleware, router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("printhub.bot")

BOT_COMMANDS = [
    BotCommand(command="sela", description="🏷️ Sela Etiketka (1-qadam)"),
    BotCommand(command="val", description="⚙️ Stiker Val Montaji (2-qadam)"),
    BotCommand(command="varaq", description="📄 Varaq Montaji (Ofset/Raqamli)"),
    BotCommand(command="ai", description="✨ AI Dizayn (Claude + VectorCraft)"),
    BotCommand(command="menu", description="🏠 Bosh menyu"),
    BotCommand(command="cancel", description="❌ Joriy amalni bekor qilish"),
]


async def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN o'rnatilmagan! Bot ishga tushirilmadi.")
        sys.exit(0)

    bot = Bot(
        token=TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(WhitelistMiddleware())
    dp.callback_query.middleware(WhitelistMiddleware())
    dp.include_router(router)

    try:
        await bot.set_my_commands(BOT_COMMANDS)
    except Exception as exc:
        logger.warning("Bot buyruqlarini o'rnatishda xatolik: %s", exc)

    logger.info("PrintHub Telegram Bot ishga tushmoqda...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
