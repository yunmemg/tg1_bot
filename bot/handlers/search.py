import asyncio
import json
import secrets

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..services import netease, qqmusic, qishui
from ..services.base import Song
from ..utils import cache

router = Router()

PLATFORM_NAMES = {"netease": "网易云", "qq": "QQ音乐", "qishui": "汽水"}

PAGE_SIZE = 5


def _short(s: str, n: int = 20) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


async def _search_all(keyword: str, limit: int = 5) -> dict[str, list[Song]]:
    results = {}
    tasks = {
        "netease": netease.search(keyword, limit),
        "qq": qqmusic.search(keyword, limit),
        "qishui": qishui.search(keyword, limit),
    }
    done, _ = await asyncio.wait(
        [asyncio.create_task(t, name=k) for k, t in tasks.items()],
        timeout=20,
    )
    for fut in done:
        name = fut.get_name()
        try:
            results[name] = fut.result()
        except Exception:
            results[name] = []
    return results


def _flatten(results: dict[str, list[Song]]) -> list[Song]:
    flat: list[Song] = []
    for platform in ("netease", "qq", "qishui"):
        for s in results.get(platform, []):
            flat.append(s)
    return flat


def _build_markup(res_key: str, page: int, total: int) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    for i in range(PAGE_SIZE):
        idx = page * PAGE_SIZE + i
        if idx >= total:
            break
        buttons.append(
            [InlineKeyboardButton(text=f"🎵 第 {idx + 1} 首", callback_data=f"play:{res_key}:{idx}")]
        )
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"page:{res_key}:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"page:{res_key}:{page + 1}"))
    if nav:
        buttons.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("search"))
async def cmd_search(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer("用法：/search 歌曲名 或 歌手 歌曲名")
        return
    keyword = args[1].strip()
    status = await message.answer(f"🔍 正在搜索「{keyword}」…")
    results = await _search_all(keyword)
    flat = _flatten(results)
    if not flat:
        await status.edit_text(f"未找到与「{keyword}」相关的歌曲。")
        return

    res_key = secrets.token_hex(6)
    cache.put_list(res_key, flat)

    lines = [f"🔍 搜索「{keyword}」结果（共 {len(flat)} 首）：", ""]
    for idx, s in enumerate(flat[:PAGE_SIZE]):
        lines.append(f"{idx + 1}. [{PLATFORM_NAMES[s.platform]}] {_short(s.title)} - {_short(s.artist)}")
    lines.append("")
    lines.append("点击下方按钮点歌，或翻页查看更多：")
    await status.edit_text(
        "\n".join(lines),
        reply_markup=_build_markup(res_key, 0, len(flat)),
    )


@router.message(Command("dian"))
async def cmd_dian(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer("用法：/dian 歌曲名，例如 /dian 晴天")
        return
    keyword = args[1].strip()
    status = await message.answer(f"🎧 正在点播「{keyword}」…")
    results = await _search_all(keyword, limit=1)
    flat = _flatten(results)
    if not flat:
        await status.edit_text(f"未找到与「{keyword}」相关的歌曲。")
        return

    first = flat[0]
    await _play_song(message, status, first)


async def _play_song(message: Message, status: Message, song: Song):
    from ..db import database
    from ..utils.sender import send_song

    if song.platform == "netease":
        await netease.resolve(song)
    elif song.platform == "qq":
        await qqmusic.resolve(song)
    elif song.platform == "qishui":
        await qishui.resolve(song)

    if not song.audio_url:
        hint = "发送 /login 扫码登录该平台后可完整播放。" if song.platform in ("netease", "qq") else ""
        await status.edit_text(
            f"歌曲「{song.title}」在当前平台（{PLATFORM_NAMES[song.platform]}）无法获取播放链接，"
            f"可能为付费/VIP 歌曲。{hint}请尝试其他平台搜索。"
        )
        return

    ok = await send_song(message.bot, message.chat.id, song)
    if not ok:
        await status.edit_text(f"「{song.title}」播放链接失效，请稍后再试或换首歌。")
        return

    fav_key = cache.make_key(song.platform, song.song_id)
    cache.put_song(fav_key, song)
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
        f"✅ 正在播放 [{PLATFORM_NAMES[song.platform]}] {song.title} - {song.artist}",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("play:"))
async def cb_play(callback: CallbackQuery):
    await callback.answer()
    _, res_key, idx_s = callback.data.split(":", 2)
    idx = int(idx_s)
    songs = cache.get_list(res_key)
    if not songs or idx >= len(songs):
        await callback.message.edit_text("搜索已过期，请重新搜索。")
        return
    song = songs[idx]
    status = await callback.message.edit_text(f"⏳ 正在解析「{song.title}」…")
    await _play_song(callback.message, status, song)


@router.callback_query(F.data.startswith("page:"))
async def cb_page(callback: CallbackQuery):
    await callback.answer()
    _, res_key, page_s = callback.data.split(":", 2)
    page = int(page_s)
    songs = cache.get_list(res_key)
    if not songs:
        await callback.message.edit_text("搜索已过期，请重新搜索。")
        return
    lines = [f"🔍 搜索结果（共 {len(songs)} 首）：", ""]
    for idx in range(page * PAGE_SIZE, min((page + 1) * PAGE_SIZE, len(songs))):
        s = songs[idx]
        lines.append(f"{idx + 1}. [{PLATFORM_NAMES[s.platform]}] {_short(s.title)} - {_short(s.artist)}")
    lines.append("")
    lines.append("点击下方按钮点歌，或翻页查看更多：")
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_build_markup(res_key, page, len(songs)),
    )
