from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router()

HELP_TEXT = (
    "🎵 音乐机器人使用说明\n\n"
    "/search 关键词 - 跨平台搜索歌曲（网易云/QQ/汽水音乐）\n"
    "/dian 关键词 - 直接点歌，播放最匹配的一首\n"
    "/fav - 查看我的收藏歌单\n"
    "/start - 显示欢迎信息\n"
    "/help - 显示帮助\n\n"
    "点歌后会展示搜索列表，点击选择即可播放；"
    "播放结果下方有「收藏」按钮，可加入个人歌单。"
)


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "你好！我是音乐机器人，支持网易云音乐、QQ音乐、汽水音乐点歌与搜索。\n\n"
        f"发送 /help 查看使用方法。",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT)
