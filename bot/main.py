import logging
import sys
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot, Dispatcher, Router
from aiogram.types import BotCommand, CallbackQuery, Message, TelegramObject

from .config import config
from .db import database
from .handlers import commands, favorites, login, search

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class WhitelistMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not config.ALLOWED_USER_IDS:
            return await handler(event, data)

        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user and user.id not in config.ALLOWED_USER_IDS:
            if isinstance(event, Message):
                await event.answer("抱歉，您没有使用该机器人的权限。")
            return None
        return await handler(event, data)


def _build_router() -> Router:
    root = Router()
    root.include_router(commands.router)
    root.include_router(search.router)
    root.include_router(favorites.router)
    root.include_router(login.router)
    return root


async def _setup_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="search", description="跨平台搜索歌曲"),
            BotCommand(command="dian", description="直接点歌"),
            BotCommand(command="fav", description="我的收藏歌单"),
            BotCommand(command="login", description="扫码登录平台账号"),
            BotCommand(command="login_status", description="查看登录状态"),
            BotCommand(command="help", description="使用帮助"),
        ]
    )


async def _main() -> None:
    if not config.BOT_TOKEN:
        logger.error("未配置 BOT_TOKEN，请填写环境变量")
        sys.exit(1)

    database.init_db()
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()

    dp.message.middleware(WhitelistMiddleware())
    dp.callback_query.middleware(WhitelistMiddleware())

    dp.include_router(_build_router())
    await _setup_commands(bot)

    logger.info("音乐机器人启动成功，等待消息…")
    # aiogram v3 必须使用 bot=bot 命名参数！！
    await dp.start_polling(bot=bot)


def main() -> None:
    import asyncio
    asyncio.run(_main())


if __name__ == "__main__":
    main()
