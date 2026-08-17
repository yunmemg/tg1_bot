import time
from typing import Optional

from ..services.base import Song

_MAX_TTL = 600
_cache: dict[str, tuple[float, Song]] = {}


def put(key: str, song: Song) -> None:
    _cleanup()
    _cache[key] = (time.time(), song)


def get(key: str) -> Optional[Song]:
    item = _cache.get(key)
    if not item:
        return None
    ts, song = item
    if time.time() - ts > _MAX_TTL:
        _cache.pop(key, None)
        return None
    return song


def make_key(platform: str, song_id: str) -> str:
    return f"{platform}:{song_id}"


def _cleanup() -> None:
    now = time.time()
    for key in [k for k, (ts, _) in _cache.items() if now - ts > _MAX_TTL]:
        _cache.pop(key, None)
