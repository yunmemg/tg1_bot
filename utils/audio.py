import tempfile
from pathlib import Path

import aiohttp

MAX_AUDIO_BYTES = 45 * 1024 * 1024  # Telegram 上限 50MB，留余量

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}


async def download_audio(url: str) -> Path | None:
    tmp_dir = Path(tempfile.gettempdir()) / "music_bot_audio"
    tmp_dir.mkdir(exist_ok=True)
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(url, timeout=30) as resp:
                if resp.status != 200:
                    return None
                ext = ".mp3"
                ctype = resp.headers.get("Content-Type", "")
                if "mp4" in ctype or "m4a" in ctype:
                    ext = ".m4a"
                if "mp3" in ctype:
                    ext = ".mp3"
                path = tmp_dir / f"{abs(hash(url))}{ext}"
                with open(path, "wb") as f:
                    size = 0
                    async for chunk in resp.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > MAX_AUDIO_BYTES:
                            f.close()
                            path.unlink(missing_ok=True)
                            return None
                        f.write(chunk)
        return path if path.exists() and path.stat().st_size > 0 else None
    except Exception:
        return None
