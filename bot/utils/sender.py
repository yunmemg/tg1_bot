import aiohttp
from aiogram import Bot
from aiogram.types import BufferedInputFile

from ..services.base import Song

IMG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://music.163.com/",
}


async def fetch_cover_bytes(url: str) -> bytes | None:
    if not url:
        return None
    try:
        async with aiohttp.ClientSession(headers=IMG_HEADERS) as session:
            async with session.get(url, timeout=8) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
        return data if len(data) < 5 * 1024 * 1024 else None
    except Exception:
        return None


async def send_song(bot: Bot, chat_id: int, song: Song) -> bool:
    from ..utils.audio import download_audio

    if not song.audio_url:
        return False
    path = await download_audio(song.audio_url)
    if not path:
        return False

    cover = await fetch_cover_bytes(song.cover_url)
    thumbnail = BufferedInputFile(cover, filename="cover.jpg") if cover else None

    with open(path, "rb") as f:
        await bot.send_audio(
            chat_id,
            BufferedInputFile(f.read(), filename=f"{song.title}.{path.suffix.lstrip('.')}"),
            title=song.title,
            performer=song.artist,
            thumbnail=thumbnail,
        )
    return True
