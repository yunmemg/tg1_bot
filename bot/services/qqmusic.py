import json

import aiohttp

from .base import Song

SEARCH_URL = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp"
VKEY_URL = "https://u.y.qq.com/cgi-bin/musicu.fcg"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://y.qq.com/",
    "Content-Type": "application/json",
}


async def search(keyword: str, limit: int = 10) -> list[Song]:
    params = {"w": keyword, "format": "json", "n": limit}
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(SEARCH_URL, params=params, timeout=12) as resp:
            data = await resp.json(content_type=None)
    songs = (data.get("data") or {}).get("song") or {}
    song_list = songs.get("list") or []
    result: list[Song] = []
    for s in song_list:
        singer = s.get("singer") or []
        pay = s.get("pay") or {}
        result.append(
            Song(
                platform="qq",
                title=s.get("songname", ""),
                artist=" / ".join(a.get("name", "") for a in singer),
                cover_url="",
                song_id=s.get("songmid", ""),
                duration=s.get("interval", 0) * 1000,
                extra={
                    "albummid": s.get("albummid", ""),
                    "payplay": pay.get("payplay", 1),
                },
            )
        )
    return result


async def get_audio_url(songmid: str) -> str:
    payload = {
        "req": {
            "module": "CDN.SrfCdnDispatchServer",
            "method": "GetCdnDispatch",
            "param": {"guid": "6275789634", "calltype": 0, "userip": ""},
        },
        "req_0": {
            "module": "vkey.GetVkeyServer",
            "method": "CgiGetVkey",
            "param": {
                "guid": "6275789634",
                "songmid": [songmid],
                "songtype": [0],
                "uin": "0",
                "loginflag": 1,
                "platform": "20",
            },
        },
        "comm": {"uin": 0, "format": "json", "ct": 24, "cv": 0},
    }
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.post(VKEY_URL, data=json.dumps(payload), timeout=12) as resp:
            data = await resp.json(content_type=None)
    req_0 = data.get("req_0") or {}
    d = req_0.get("data") or {}
    sip = d.get("sip") or []
    purl = ""
    for m in d.get("midurlinfo") or []:
        purl = m.get("purl") or ""
        break
    if not sip or not purl:
        return ""
    return sip[0] + purl


async def get_cover_url(albummid: str) -> str:
    if not albummid:
        return ""
    return f"https://y.gtimg.cn/music/photo_new/T002R300x300M000{albummid}.jpg"


async def resolve(song: Song) -> Song:
    song.audio_url = await get_audio_url(song.song_id)
    if not song.cover_url:
        song.cover_url = await get_cover_url(song.extra.get("albummid", ""))
    return song
