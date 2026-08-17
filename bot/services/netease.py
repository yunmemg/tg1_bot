import asyncio
import time
import urllib.parse

import aiohttp

from .base import Song
from . import crypto
from ..db import database

BASE = "https://music.163.com"
QR_KEY_API = "https://interface.music.163.com/api/login/qrcode/unikey"
QR_CHECK_API = "https://interface.music.163.com/api/login/qrcode/client/login"
PLAYER_API = "https://interface3.music.163.com/eapi/song/enhance/player/url/v1"
WAPI_PLAYER_API = "https://music.163.com/api/song/enhance/player/url"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://music.163.com/",
}

# 免费歌曲可离线完整播放；VIP(1)/付费下载(8) 需登录态
FREE_FEES = {0}


def _cookie_str(cookie: str) -> str:
    return cookie


async def search(keyword: str, limit: int = 10) -> list[Song]:
    params = {"s": keyword, "type": 1, "offset": 0, "limit": limit}
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(f"{BASE}/api/search/get/web", params=params, timeout=12) as resp:
            data = await resp.json(content_type=None)
    songs = (data.get("result") or {}).get("songs") or []
    result: list[Song] = []
    for s in songs:
        fee = s.get("fee", 0)
        result.append(
            Song(
                platform="netease",
                title=s.get("name", ""),
                artist=" / ".join(a.get("name", "") for a in s.get("artists", [])),
                cover_url="",
                song_id=str(s.get("id", "")),
                duration=s.get("duration", 0),
                extra={"fee": fee},
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
        extra={"fee": s.get("fee", 0)},
    )


async def _fetch_cookie() -> str:
    cred = database.get_credential("netease")
    if not cred:
        return ""
    return cred[0] or ""


async def _post_form(url: str, data: dict, cookie: str = "") -> tuple[aiohttp.ClientResponse, bytes]:
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if cookie:
            headers["Cookie"] = cookie
        async with session.post(
            url,
            data=urllib.parse.urlencode(data),
            headers=headers,
            timeout=12,
        ) as resp:
            return resp, await resp.read()


async def _eapi_player_url(song_id: str, cookie: str) -> str:
    payload = {
        "ids": [int(song_id)],
        "level": "standard",
        "encodeType": "mp3",
        "header": '{"os":"pc","appver":"","osver":"","deviceId":"pyncm!","requestId":"12345678"}',
    }
    params = crypto.eapi_params(PLAYER_API, payload)
    data = urllib.parse.urlencode({"params": params})
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.post(
            PLAYER_API,
            data=data,
            headers={"Cookie": cookie, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=12,
        ) as resp:
            body = await resp.text()
    try:
        import json

        parsed = json.loads(body)
    except Exception:
        return ""
    items = parsed.get("data") or []
    if not items:
        return ""
    return items[0].get("url", "") or ""


async def get_audio_url(song_id: str, fee: int = 0, cookie: str = "") -> str:
    cookie = cookie or await _fetch_cookie()
    if fee not in FREE_FEES:
        if not cookie:
            return ""
        url = await _eapi_player_url(song_id, cookie)
        if url:
            return url
        return ""
    return f"{BASE}/song/media/outer/url?id={song_id}.mp3"


async def resolve(song: Song) -> Song:
    cookie = await _fetch_cookie()
    fee = int(song.extra.get("fee", 0)) if song.extra else 0
    song.audio_url = await get_audio_url(song.song_id, fee, cookie)
    if not song.cover_url:
        detail = await get_detail(song.song_id)
        if detail:
            song.cover_url = detail.cover_url
    return song


# ---------------- 扫码登录 ----------------

async def create_qr_login() -> dict:
    data = {"type": "3"}
    resp, body = await _post_form(QR_KEY_API, data)
    try:
        import json

        parsed = json.loads(body)
    except Exception:
        raise RuntimeError("网易云二维码获取失败")
    if parsed.get("code") != 200:
        raise RuntimeError(f"网易云二维码获取失败: {parsed.get('message', 'unknown')}")
    unikey = parsed.get("unikey", "")
    return {
        "key": unikey,
        "url": f"https://music.163.com/login?codekey={urllib.parse.quote(unikey)}",
        "expires_at": time.time() + 300,
    }


async def check_qr_login(key: str) -> dict:
    data = {"key": key, "type": "3"}
    resp, body = await _post_form(QR_CHECK_API, data)
    try:
        import json

        parsed = json.loads(body)
    except Exception:
        raise RuntimeError("网易云扫码状态查询失败")
    code = parsed.get("code", -1)
    cookie = parsed.get("cookie", "")
    status_map = {
        800: "expired",
        801: "waiting",
        802: "scanned",
        803: "success",
    }
    status = status_map.get(code, "failed")
    if status == "success":
        if not cookie:
            return {"status": "failed", "message": "登录成功但未返回 cookie，请重试"}
        database.save_credential("netease", cookie)
    return {
        "status": status,
        "message": parsed.get("message", ""),
        "cookie": cookie,
    }


# ---------------- 登录状态查询 ----------------

def get_login_status() -> dict | None:
    cred = database.get_credential("netease")
    if not cred:
        return None
    return {"cookie": cred[0], "extra": cred[1]}


def logout() -> None:
    database.delete_credential("netease")
