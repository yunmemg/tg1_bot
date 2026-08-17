import sqlite3
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
