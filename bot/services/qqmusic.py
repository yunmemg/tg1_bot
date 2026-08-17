import asyncio
import json
import random
import re
import time

import aiohttp

from .base import Song
from ..db import database

SEARCH_URL = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp"
VKEY_URL = "https://u.y.qq.com/cgi-bin/musicu.fcg"
QR_SHOW_API = "https://ssl.ptlogin2.qq.com/ptqrshow"
QR_CHECK_API = "https://ssl.ptlogin2.qq.com/ptqrlogin"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://y.qq.com/",
    "Content-Type": "application/json",
}

# 登录后可请求的音质前缀（mp3 优先，避免 FLAC 过大超出 Telegram 限制）
VIP_FILENAMES = ["M800", "M500"]
FREE_FILENAMES = ["M800", "M500"]
VIP_EXTS = ["mp3", "mp3"]
FREE_EXTS = ["mp3", "mp3"]


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


async def _fetch_cookie() -> tuple[str, dict]:
    cred = database.get_credential("qq")
    if not cred:
        return "", {}
    return cred[0], cred[1]


async def get_audio_url(songmid: str, cookie: str = "") -> str:
    if cookie:
        url = await _get_vkey_login(songmid, cookie)
        if url:
            return url
    return await _get_vkey_anon(songmid)


async def _get_vkey_anon(songmid: str) -> str:
    return await _url_get_vkey(songmid, "")


async def _url_get_vkey(songmid: str, cookie: str) -> str:
    cred = database.get_credential("qq")
    extra = cred[1] if cred else {}
    is_vip = bool(extra.get("is_vip"))

    prefixes = VIP_FILENAMES if is_vip else FREE_FILENAMES
    exts = VIP_EXTS if is_vip else FREE_EXTS
    filenames = [
        f"{p}{songmid}{songmid}.{e}" for p, e in zip(prefixes, exts)
    ]
    guid = str(random.randint(1000000000, 9999999999))

    payload = {
        "comm": {
            "cv": 4747474,
            "ct": 24,
            "format": "json",
            "inCharset": "utf-8",
            "outCharset": "utf-8",
            "notice": 0,
            "platform": "yqq.json",
            "needNewCode": 1,
            "uin": 0,
        },
        "req_1": {
            "module": "music.vkey.GetVkey",
            "method": "UrlGetVkey",
            "param": {
                "guid": guid,
                "songmid": [songmid] * len(filenames),
                "songtype": [0] * len(filenames),
                "uin": "0",
                "loginflag": 1,
                "platform": "20",
                "filename": filenames,
            },
        },
    }
    headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": "https://y.qq.com/",
        "Content-Type": "application/json",
    }
    if cookie:
        headers["Cookie"] = cookie
    async with aiohttp.ClientSession() as session:
        async with session.post(VKEY_URL, data=json.dumps(payload), headers=headers, timeout=12) as resp:
            data = await resp.json(content_type=None)
    req_1 = data.get("req_1") or {}
    infos = ((req_1.get("data") or {}).get("midurlinfo")) or []
    for expected in filenames:
        for info in infos:
            purl = info.get("purl") or ""
            if info.get("filename") == expected and purl:
                return "https://ws.stream.qqmusic.qq.com/" + purl
    return ""


async def _get_vkey_login(songmid: str, cookie: str) -> str:
    return await _url_get_vkey(songmid, cookie)


async def get_cover_url(albummid: str) -> str:
    if not albummid:
        return ""
    return f"https://y.gtimg.cn/music/photo_new/T002R300x300M000{albummid}.jpg"


async def resolve(song: Song) -> Song:
    cookie, _ = await _fetch_cookie()
    song.audio_url = await get_audio_url(song.song_id, cookie)
    if not song.cover_url:
        song.cover_url = await get_cover_url(song.extra.get("albummid", ""))
    return song


# ---------------- 扫码登录 ----------------

def _hash33(s: str) -> int:
    h = 0
    for c in s:
        h = (h << 5) + h + ord(c)
    return h & 0x7FFFFFFF


async def create_qr_login() -> dict:
    t = f"{time.time_ns() / 1e18:.17f}"
    params = {
        "appid": "716027609",
        "e": "2",
        "l": "M",
        "s": "3",
        "d": "72",
        "v": "4",
        "t": t,
        "daid": "383",
        "pt_3rd_aid": "100497308",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(
            QR_SHOW_API,
            params=params,
            headers={"User-Agent": HEADERS["User-Agent"], "Referer": "https://y.qq.com/"},
            timeout=12,
        ) as resp:
            img = await resp.read()
            qrsig = (resp.cookies.get("qrsig").value) if resp.cookies.get("qrsig") else ""
    if not qrsig:
        raise RuntimeError("QQ 二维码获取失败：未返回 qrsig")
    import base64

    return {
        "key": f"qrsig={qrsig}",
        "image_base64": base64.b64encode(img).decode(),
        "qrsig": qrsig,
        "expires_at": time.time() + 120,
    }


def _parse_qr_check(raw: str) -> tuple[str, str, str]:
    m = re.findall(r"'([^']*)'", raw)
    if len(m) >= 5:
        return m[0], m[4], m[2]
    return "", raw, ""


async def _fetch_redirect_cookies(
    session: aiohttp.ClientSession, redirect_url: str
) -> dict:
    collected = {}
    current = redirect_url
    referer = "https://y.qq.com/"
    for _ in range(8):
        if not current:
            break
        try:
            cookie_header = _jar_to_cookie_str(session.cookie_jar)
            async with session.get(
                current,
                allow_redirects=False,
                headers={
                    "User-Agent": HEADERS["User-Agent"],
                    "Referer": referer,
                    "Cookie": cookie_header,
                },
                timeout=12,
            ) as resp:
                for c in resp.cookies.values():
                    collected[c.key] = c.value
                location = resp.headers.get("Location", "")
                if not location or not (300 <= resp.status < 400):
                    break
                from urllib.parse import urljoin

                current = (
                    location if location.startswith("http") else urljoin(current, location)
                )
                referer = current
        except (aiohttp.ClientError, asyncio.TimeoutError):
            break
    return collected


def _jar_to_cookie_str(jar: aiohttp.CookieJar) -> str:
    seen = set()
    parts = []
    for m in jar:
        key = m.key
        if key in seen:
            continue
        seen.add(key)
        parts.append(f"{key}={m.value}")
    return "; ".join(sorted(parts))


async def check_qr_login(key: str) -> dict:
    import asyncio
    from urllib.parse import parse_qs, urlencode

    values = parse_qs(key)
    qrsig = (values.get("qrsig") or [""])[0]
    if not qrsig:
        return {"status": "failed", "message": "缺少 qrsig"}

    params = {
        "u1": "https://graph.qq.com/oauth2.0/login_jump",
        "ptqrtoken": str(_hash33(qrsig)),
        "ptredirect": "100",
        "h": "1",
        "t": "1",
        "g": "1",
        "from_ui": "1",
        "ptlang": "2052",
        "action": f"0-0-{int(time.time() * 1000)}",
        "js_ver": "21072115",
        "js_type": "1",
        "login_sig": "",
        "pt_uistyle": "40",
        "aid": "716027609",
        "daid": "383",
        "pt_3rd_aid": "100497308",
        "has_onekey": "1",
        "pttype": "1",
        "service": "ptqrlogin",
        "nodirect": "0",
    }
    qs = urlencode(params)

    # 关闭自动重定向，手动接管 302，避免丢失中间 Set-Cookie
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        jar.update_cookies({"qrsig": qrsig})
        try:
            async with session.get(
                f"{QR_CHECK_API}?{qs}",
                allow_redirects=False,
                headers={
                    "User-Agent": HEADERS["User-Agent"],
                    "Referer": "https://xui.ptlogin2.qq.com/",
                },
                timeout=12,
            ) as resp:
                raw = await resp.text()
                status_code = resp.status
                location = resp.headers.get("Location", "")
        except asyncio.TimeoutError:
            return {"status": "failed", "message": "QQ 扫码查询超时，请重试"}
        except aiohttp.ClientError as e:
            return {"status": "failed", "message": f"QQ 扫码查询网络错误: {e}"}

        # 直接 302/303/307/308 = 登录成功，跳过 ptuiCB 文本解析
        if status_code in (301, 302, 303, 307, 308):
            redirect_url = location
        else:
            code, message, redirect_url = _parse_qr_check(raw)
            status_map = {"0": "success", "65": "expired", "66": "waiting", "67": "scanned"}
            status = status_map.get(code, "failed")
            if status != "success":
                return {"status": status, "message": message or raw.strip()}
            if not redirect_url:
                redirect_url = location

        redirect_cookies = await _fetch_redirect_cookies(session, redirect_url)
        all_cookies = {c.key: c.value for c in jar}
        all_cookies.update(redirect_cookies)

        uin = (
            all_cookies.get("uin")
            or all_cookies.get("pt2gguin")
            or all_cookies.get("p_uin")
            or ""
        )
        qqmusic_key = (
            all_cookies.get("qqmusic_key")
            or all_cookies.get("p_skey")
            or all_cookies.get("skey")
            or all_cookies.get("musickey")
            or ""
        )
        if not qqmusic_key:
            return {"status": "failed", "message": "登录成功但未获取到音乐 key，请重试"}

        cookie_parts = []
        for k, v in all_cookies.items():
            if k and v:
                cookie_parts.append(f"{k}={v}")
        cookie_str = "; ".join(sorted(cookie_parts))

        is_vip = bool(uin) and bool(qqmusic_key)
        try:
            database.save_credential("qq", cookie_str, {"uin": uin, "is_vip": is_vip})
        except Exception:
            return {"status": "failed", "message": "登录成功但凭证保存失败，请重试"}
        return {"status": "success", "message": "登录成功", "cookie": cookie_str}


# ---------------- 登录状态查询 ----------------

def get_login_status() -> dict | None:
    cred = database.get_credential("qq")
    if not cred:
        return None
    return {"cookie": cred[0], "extra": cred[1]}


def logout() -> None:
    database.delete_credential("qq")
