import json
import time

from ..db import database
from ..services.base import Song

# 搜索结果缓存有效期：24 小时
MAX_TTL = 24 * 3600


def _song_to_dict(song: Song) -> dict:
    return {
        "platform": song.platform,
        "title": song.title,
        "artist": song.artist,
        "cover_url": song.cover_url,
        "audio_url": song.audio_url,
        "song_id": song.song_id,
        "duration": song.duration,
        "extra": song.extra,
    }


def _dict_to_song(d: dict) -> Song:
    return Song(
        platform=d.get("platform", ""),
        title=d.get("title", ""),
        artist=d.get("artist", ""),
        cover_url=d.get("cover_url", ""),
        audio_url=d.get("audio_url", ""),
        song_id=d.get("song_id", ""),
        duration=d.get("duration", 0),
        extra=d.get("extra", {}) or {},
    )


def put_list(key: str, songs: list[Song]) -> None:
    database.save_search_cache(key, [_song_to_dict(s) for s in songs])


def get_list(key: str) -> list[Song] | None:
    raw = database.get_search_cache(key, MAX_TTL)
    if raw is None:
        return None
    try:
        return [_dict_to_song(d) for d in json.loads(raw)]
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


def put_song(key: str, song: Song) -> None:
    database.save_search_cache(key, [_song_to_dict(song)])


def get_song(key: str) -> Song | None:
    raw = database.get_search_cache(key, MAX_TTL)
    if raw is None:
        return None
    try:
        items = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not items:
        return None
    return _dict_to_song(items[0])


def make_key(platform: str, song_id: str) -> str:
    return f"{platform}:{song_id}"
