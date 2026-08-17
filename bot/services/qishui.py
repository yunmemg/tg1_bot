import re

import aiohttp

from .base import Song

SEARCH_URL = "https://api.suyanw.cn/api/qishuimusic.php"
PEAR_URL = "https://api.pearapi.ai/api/qishui_music"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}


async def search(keyword: str, limit: int = 10) -> list[Song]:
    params = {"msg": keyword, "n": ""}
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(SEARCH_URL, params=params, timeout=12) as resp:
            data = await resp.json(content_type=None)
    items = data.get("data") or []
    if not isinstance(items, list):
        return []
    result: list[Song] = []
    for i in items[:limit]:
        result.append(
            Song(
                platform="qishui",
                title=i.get("title", ""),
                artist=i.get("singer", ""),
                song_id="",
                extra={"n": i.get("n"), "keyword": keyword},
            )
        )
    return result


async def _get_track_id(session: aiohttp.ClientSession, keyword: str, n) -> str:
    params = {"msg": keyword, "n": str(n)}
    async with session.get(SEARCH_URL, params=params, timeout=12) as resp:
        data = await resp.json(content_type=None)
    link = data.get("link") or ""
    m = re.search(r"track_id=(\d+)", link)
    return m.group(1) if m else ""


async def resolve(song: Song) -> Song:
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        track_id = song.song_id
        if not track_id:
            keyword = song.extra.get("keyword", "")
            n = song.extra.get("n")
            if keyword and n is not None:
                track_id = await _get_track_id(session, keyword, n)
        if not track_id:
            return song
        song.song_id = track_id
        async with session.get(PEAR_URL, params={"id": track_id}, timeout=15) as resp:
            pear = await resp.json(content_type=None)
    if pear.get("code") == 200:
        d = pear.get("data") or {}
        song.title = d.get("song_name") or song.title
        song.artist = d.get("singers") or song.artist
        song.cover_url = d.get("cover") or ""
        song.audio_url = d.get("url") or ""
    return song
