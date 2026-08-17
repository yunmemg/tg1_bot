from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router()

HELP_TEXT = (
    "🎵 音乐机器人使用说明\n\n"
    "/search 关键词 - 跨平台搜索歌曲（网易云/QQ/汽水音乐）\n"
    "/dian 关键词 - 直接点歌，播放最匹配的一首\n"
    "/fav - 查看我的收藏歌单\n"
    "/login - 管理员扫码登录网易云/QQ音乐，解锁 VIP/会员歌曲完整播放\n"
    "/logincookie qq|netease <Cookie> - 管理员手动粘贴 Cookie 登录（扫码失效时的备选）\n"
    "/login_status - 查看各平台登录状态\n"
    "/start - 显示欢迎信息\n"
    "/help - 显示帮助\n\n"
    "管理员登录后，所有用户点歌都会使用会员权限解析完整时长音频；"
    "未登录的付费歌曲会提示换平台。"
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
