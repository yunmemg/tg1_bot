import aiohttp

from .base import Song

BASE = "https://music.163.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://music.163.com/",
}


async def search(keyword: str, limit: int = 10) -> list[Song]:
    params = {"s": keyword, "type": 1, "offset": 0, "limit": limit}
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(f"{BASE}/api/search/get/web", params=params, timeout=12) as resp:
            data = await resp.json(content_type=None)
    songs = (data.get("result") or {}).get("songs") or []
    result: list[Song] = []
    for s in songs:
        result.append(
            Song(
                platform="netease",
                title=s.get("name", ""),
                artist=" / ".join(a.get("name", "") for a in s.get("artists", [])),
                cover_url="",
                song_id=str(s.get("id", "")),
                duration=s.get("duration", 0),
            )
        )
    return result


async def get_detail(song_id: str) -> Song | None:
    params = {"ids": f"[{song_id}]"}
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(f"{BASE}/api/song/detail", params=params, timeout=12) as resp:
            data = await resp.json(content_type=None)
    songs = data.get("songs") or []
    if not songs:
        return None
    s = songs[0]
    album = s.get("album") or {}
    return Song(
        platform="netease",
        title=s.get("name", ""),
        artist=" / ".join(a.get("name", "") for a in s.get("artists", [])),
        cover_url=album.get("picUrl", ""),
        song_id=str(s.get("id", "")),
        duration=s.get("duration", 0),
    )


async def get_audio_url(song_id: str) -> str:
    return f"{BASE}/song/media/outer/url?id={song_id}.mp3"


async def resolve(song: Song) -> Song:
    song.audio_url = await get_audio_url(song.song_id)
    if not song.cover_url:
        detail = await get_detail(song.song_id)
        if detail:
            song.cover_url = detail.cover_url
    return song
