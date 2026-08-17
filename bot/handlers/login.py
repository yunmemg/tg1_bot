import asyncio
import base64
import io
import logging
import time

import qrcode
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..config import config
from ..services import netease, qqmusic

router = Router()
logger = logging.getLogger(__name__)

PLATFORM_NAMES = {"netease": "网易云音乐", "qq": "QQ音乐"}

# 轮询间隔（秒）
POLL_INTERVAL = 2.5
# 总超时（秒）
POLL_TIMEOUT = 180


def _is_admin(user_id: int) -> bool:
    if not config.ADMIN_IDS:
        return True
    return user_id in config.ADMIN_IDS


def _qr_image_from_url(url: str) -> BufferedInputFile:
    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return BufferedInputFile(buf.read(), filename="qr.png")


def _qr_image_from_base64(b64: str) -> BufferedInputFile:
    return BufferedInputFile(base64.b64decode(b64), filename="qr.png")


@router.message(Command("login"))
async def cmd_login(message: Message):
    if not _is_admin(message.from_user.id):
        await message.answer("该操作仅限管理员执行，普通用户点歌时会自动使用已登录的账号。")
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="网易云音乐",
                    callback_data="login:netease",
                ),
                InlineKeyboardButton(
                    text="QQ音乐",
                    callback_data="login:qq",
                ),
            ]
        ]
    )
    await message.answer(
        "🔐 请选择要登录的平台（登录后 VIP/会员歌曲可完整播放）：\n\n"
        "⚠️ 凭证仅保存在你自己的服务器数据库中，不会泄露。",
        reply_markup=kb,
    )


@router.message(Command("logincookie"))
async def cmd_logincookie(message: Message):
    if not _is_admin(message.from_user.id):
        await message.answer("该操作仅限管理员执行。")
        return
    usage = (
        "📋 请提供平台和 Cookie，格式：\n"
        "/logincookie qq <Cookie值>\n"
        "/logincookie netease <Cookie值>\n\n"
        "获取方法：电脑浏览器登录 y.qq.com 或 music.163.com，"
        "按 F12 → Network → 刷新页面 → 点击任意请求 → 复制请求头里的 Cookie 值。"
    )
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(usage)
        return
    platform = parts[1].strip().lower()
    cookie = parts[2].strip()
    if platform == "netease":
        ok, msg = netease.save_cookie(cookie)
    elif platform == "qq":
        ok, msg = qqmusic.save_cookie(cookie)
    else:
        await message.answer(usage)
        return
    await message.answer(("✅ " if ok else "❌ ") + msg)


@router.message(Command("logout"))
async def cmd_logout(message: Message):
    if not _is_admin(message.from_user.id):
        await message.answer("该操作仅限管理员执行。")
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="网易云音乐", callback_data="logout:netease"),
                InlineKeyboardButton(text="QQ音乐", callback_data="logout:qq"),
            ]
        ]
    )
    await message.answer("🔓 请选择要退出登录的平台：", reply_markup=kb)


@router.message(Command("login_status"))
async def cmd_login_status(message: Message):
    if not _is_admin(message.from_user.id):
        await message.answer("该操作仅限管理员执行。")
        return
    lines = ["📊 各平台登录状态：", ""]
    for key, name in PLATFORM_NAMES.items():
        cred = None
        if key == "netease":
            cred = netease.get_login_status()
        elif key == "qq":
            cred = qqmusic.get_login_status()
        if cred:
            lines.append(f"✅ {name}：已登录")
        else:
            lines.append(f"❌ {name}：未登录")
    await message.answer("\n".join(lines))


@router.callback_query(F.data.startswith("login:"))
async def cb_login(callback: CallbackQuery):
    await callback.answer()
    if not _is_admin(callback.from_user.id):
        await callback.message.edit_text("该操作仅限管理员执行。")
        return
    platform = callback.data.split(":", 1)[1]
    if platform not in PLATFORM_NAMES:
        return
    name = PLATFORM_NAMES[platform]

    try:
        if platform == "netease":
            qr = await netease.create_qr_login()
            key = qr["key"]
            img = _qr_image_from_url(qr["url"])
        else:
            qr = await qqmusic.create_qr_login()
            key = qr["key"]
            img = _qr_image_from_base64(qr["image_base64"])
    except RuntimeError as e:
        await callback.message.edit_text(f"⚠️ {e}")
        return

    sent = await callback.message.answer_photo(
        img,
        caption=f"📱 请使用{name} App 扫描上方二维码登录\n\n"
        "登录完成后会自动保存凭证，请勿关闭本消息。",
    )
    await callback.message.delete()

    started = time.monotonic()
    consecutive_errors = 0
    while True:
        if time.monotonic() - started > POLL_TIMEOUT:
            await sent.edit_caption(
                f"⏰ {name} 扫码超时（{POLL_TIMEOUT // 60} 分钟），请重新发送 /login。"
            )
            return
        await asyncio.sleep(POLL_INTERVAL)
        try:
            if platform == "netease":
                result = await netease.check_qr_login(key)
            else:
                result = await qqmusic.check_qr_login(key)
        except Exception as e:
            logger.warning(f"{name} 扫码状态查询异常: {e}")
            consecutive_errors += 1
            if consecutive_errors >= 5:
                await sent.edit_caption(f"⚠️ {name} 扫码状态查询连续失败，请稍后重试 /login。")
                return
            continue
        consecutive_errors = 0

        status = result.get("status")
        if status == "success":
            await sent.edit_caption(
                f"✅ {name} 登录成功！所有用户点歌时将使用该账号解析完整时长音频。"
            )
            return
        if status == "expired":
            await sent.edit_caption(f"⏰ {name} 二维码已过期，请重新发送 /login。")
            return
        if status == "failed":
            await sent.edit_caption(
                f"❌ {name} 登录失败：{result.get('message', '未知错误')}"
            )
            return


@router.callback_query(F.data.startswith("logout:"))
async def cb_logout(callback: CallbackQuery):
    await callback.answer()
    if not _is_admin(callback.from_user.id):
        await callback.message.edit_text("该操作仅限管理员执行。")
        return
    platform = callback.data.split(":", 1)[1]
    if platform not in PLATFORM_NAMES:
        return
    name = PLATFORM_NAMES[platform]
    if platform == "netease":
        netease.logout()
    elif platform == "qq":
        qqmusic.logout()
    await callback.message.edit_text(f"🔓 已退出 {name} 登录。")
