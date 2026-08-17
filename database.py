import sqlite3
import time
from pathlib import Path

from ..config import config

if config.DB_PATH:
    DB_PATH = Path(config.DB_PATH)
else:
    DB_PATH = Path(__file__).resolve().parent.parent.parent / "musicbot.db"


def _ensure_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _conn() -> sqlite3.Connection:
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                song_id TEXT NOT NULL,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                cover_url TEXT DEFAULT '',
                extra TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                UNIQUE(user_id, platform, song_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS search_cache (
                key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS credentials (
                platform TEXT PRIMARY KEY,
                cookie TEXT NOT NULL,
                extra TEXT DEFAULT '{}',
                updated_at TEXT DEFAULT (datetime('now','localtime'))
            )
            """
        )


def add_favorite(
    user_id: int,
    platform: str,
    song_id: str,
    title: str,
    artist: str,
    cover_url: str = "",
    extra: str = "{}",
) -> bool:
    try:
        with _conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO favorites
                (user_id, platform, song_id, title, artist, cover_url, extra)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, platform, song_id, title, artist, cover_url, extra),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def list_favorites(user_id: int) -> list[sqlite3.Row]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM favorites WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    return rows


def remove_favorite(user_id: int, fav_id: int) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "DELETE FROM favorites WHERE user_id = ? AND id = ?",
            (user_id, fav_id),
        )
    return cur.rowcount > 0


def has_favorite(user_id: int, platform: str, song_id: str) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM favorites WHERE user_id = ? AND platform = ? AND song_id = ?",
            (user_id, platform, song_id),
        ).fetchone()
    return row is not None


def save_search_cache(key: str, data: list[dict]) -> None:
    import json as _json

    with _conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO search_cache (key, data, created_at)
            VALUES (?, ?, ?)
            """,
            (key, _json.dumps(data, ensure_ascii=False), time.time()),
        )


def get_search_cache(key: str, ttl: int) -> str | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT data, created_at FROM search_cache WHERE key = ?",
            (key,),
        ).fetchone()
    if not row:
        return None
    created_at = row["created_at"]
    if time.time() - created_at > ttl:
        with _conn() as conn:
            conn.execute("DELETE FROM search_cache WHERE key = ?", (key,))
        return None
    return row["data"]


def save_credential(platform: str, cookie: str, extra: dict | None = None) -> None:
    import json as _json

    with _conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO credentials (platform, cookie, extra, updated_at)
            VALUES (?, ?, ?, datetime('now','localtime'))
            """,
            (platform, cookie, _json.dumps(extra or {}, ensure_ascii=False)),
        )


def get_credential(platform: str) -> tuple[str, dict] | None:
    import json as _json

    with _conn() as conn:
        row = conn.execute(
            "SELECT cookie, extra FROM credentials WHERE platform = ?",
            (platform,),
        ).fetchone()
    if not row:
        return None
    try:
        extra = _json.loads(row["extra"] or "{}")
    except (json.JSONDecodeError, TypeError):
        extra = {}
    return row["cookie"], extra


def list_credentials() -> dict[str, str]:
    with _conn() as conn:
        rows = conn.execute("SELECT platform, updated_at FROM credentials").fetchall()
    return {r["platform"]: r["updated_at"] for r in rows}


def delete_credential(platform: str) -> bool:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM credentials WHERE platform = ?", (platform,))
    return cur.rowcount > 0
