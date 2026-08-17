import json
import time

_favorites: list[dict] = []
_fav_counter = 0
_search_cache: dict[str, tuple[str, float]] = {}
_credentials: dict[str, dict] = {}


def init_db() -> None:
    pass


def add_favorite(
    user_id: int,
    platform: str,
    song_id: str,
    title: str,
    artist: str,
    cover_url: str = "",
    extra: str = "{}",
) -> bool:
    global _fav_counter
    for row in _favorites:
        if row["user_id"] == user_id and row["platform"] == platform and row["song_id"] == song_id:
            return True
    _fav_counter += 1
    _favorites.append(
        {
            "id": _fav_counter,
            "user_id": user_id,
            "platform": platform,
            "song_id": song_id,
            "title": title,
            "artist": artist,
            "cover_url": cover_url,
            "extra": extra,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    return True


def list_favorites(user_id: int) -> list[dict]:
    rows = [r for r in _favorites if r["user_id"] == user_id]
    rows.sort(key=lambda r: r["id"], reverse=True)
    return rows


def remove_favorite(user_id: int, fav_id: int) -> bool:
    for i, row in enumerate(_favorites):
        if row["user_id"] == user_id and row["id"] == fav_id:
            del _favorites[i]
            return True
    return False


def has_favorite(user_id: int, platform: str, song_id: str) -> bool:
    return any(
        r["user_id"] == user_id and r["platform"] == platform and r["song_id"] == song_id
        for r in _favorites
    )


def save_search_cache(key: str, data: list[dict]) -> None:
    _search_cache[key] = (json.dumps(data, ensure_ascii=False), time.time())


def get_search_cache(key: str, ttl: int) -> str | None:
    item = _search_cache.get(key)
    if not item:
        return None
    data, created_at = item
    if time.time() - created_at > ttl:
        _search_cache.pop(key, None)
        return None
    return data


def save_credential(platform: str, cookie: str, extra: dict | None = None) -> None:
    _credentials[platform] = {
        "cookie": cookie,
        "extra": extra or {},
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_credential(platform: str) -> tuple[str, dict] | None:
    item = _credentials.get(platform)
    if not item:
        return None
    return item["cookie"], dict(item["extra"])


def list_credentials() -> dict[str, str]:
    return {p: item["updated_at"] for p, item in _credentials.items()}


def delete_credential(platform: str) -> bool:
    return _credentials.pop(platform, None) is not None
