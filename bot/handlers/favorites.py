import json

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..db import database
from ..services import netease, qqmusic, qishui
from ..services.base import Song
from ..utils import cache
from ..utils.sender import send_song

router = Router()

PLATFORM_NAMES = {"netease": "网易云", "qq": "QQ音乐", "qishui": "汽水"}


def _song_from_db(row) -> Song:
    extra = {}
    try:
        extra = json.loads(row["extra"] or "{}")
    except (json.JSONDecodeError, TypeError):
        extra = {}
    return Song(
        platform=row["platform"],
        title=row["title"],
        artist=row["artist"],
        cover_url=row["cover_url"],
        song_id=row["song_id"],
        extra=extra,
    )


@router.callback_query(F.data.startswith("fav:"))
async def cb_favorite(callback: CallbackQuery):
    await callback.answer()
    _, platform, song_id = callback.data.split(":", 2)
    key = cache.make_key(platform, song_id)
    song = cache.get_song(key)
    if not song:
        await callback.message.answer("收藏信息已过期，请重新播放后再收藏。")
        return
    database.add_favorite(
        user_id=callback.from_user.id,
        platform=song.platform,
        song_id=song.song_id,
        title=song.title,
        artist=song.artist,
        cover_url=song.cover_url,
        extra=json.dumps(song.extra, ensure_ascii=False),
    )
    await callback.message.answer(
        f"✅ 已收藏：{song.title} - {song.artist}（{PLATFORM_NAMES.get(song.platform, song.platform)}）\n"
        f"发送 /fav 查看你的歌单。"
    )


@router.message(Command("fav"))
async def cmd_fav(message: Message):
    rows = database.list_favorites(message.from_user.id)
    if not rows:
        await message.answer("你的歌单还是空的，搜索歌曲播放后可点击「收藏」添加。")
        return
    lines = [f"📀 我的收藏（{len(rows)} 首）：", ""]
    kb_buttons: list[list[InlineKeyboardButton]] = []
    for row in rows:
        lines.append(
            f"{row['id']}. [{PLATFORM_NAMES.get(row['platform'], row['platform'])}] "
            f"{row['title']} - {row['artist']}"
        )
        kb_buttons.append(
            [
                InlineKeyboardButton(text=f"▶️ {row['id']}. {row['title']}", callback_data=f"playfav:{row['id']}"),
                InlineKeyboardButton(text="🗑", callback_data=f"delfav:{row['id']}"),
            ]
        )
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    await message.answer("\n".join(lines), reply_markup=kb)


@router.callback_query(F.data.startswith("playfav:"))
async def cb_playfav(callback: CallbackQuery):
    await callback.answer()
    fav_id = int(callback.data.split(":", 1)[1])
    rows = database.list_favorites(callback.from_user.id)
    row = next((r for r in rows if r["id"] == fav_id), None)
    if not row:
        await callback.message.answer("收藏不存在或已被删除。")
        return
    song = _song_from_db(row)
    status = await callback.message.answer(f"⏳ 正在解析「{song.title}」…")

    if song.platform == "netease":
        await netease.resolve(song)
    elif song.platform == "qq":
        await qqmusic.resolve(song)
    elif song.platform == "qishui":
        await qishui.resolve(song)

    if not song.audio_url:
        hint = "请管理员发送 /login 登录该平台后可完整播放。" if song.platform in ("netease", "qq") else ""
        await status.edit_text(f"「{song.title}」播放链接失效，可能为付费歌曲或已下架。{hint}")
        return

    ok = await send_song(callback.message.bot, callback.message.chat.id, song)
    if not ok:
        await status.edit_text(f"「{song.title}」播放链接失效，请稍后再试。")
        return
    key = cache.make_key(song.platform, song.song_id)
    cache.put_song(key, song)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❤️ 收藏",
                    callback_data=f"fav:{song.platform}:{song.song_id}",
                )
            ]
        ]
    )
    await status.edit_text(
        f"✅ 正在播放 [{PLATFORM_NAMES.get(song.platform, song.platform)}] {song.title} - {song.artist}",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("delfav:"))
async def cb_delfav(callback: CallbackQuery):
    await callback.answer()
    fav_id = int(callback.data.split(":", 1)[1])
    ok = database.remove_favorite(callback.from_user.id, fav_id)
    if ok:
        await callback.message.edit_text(f"已从歌单中删除第 {fav_id} 首。")
    else:
        await callback.message.answer("删除失败或收藏不存在。")
