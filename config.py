# Copyright (c) 2026 秦屿泊 (@qinyubo)
# SPDX-License-Identifier: MIT
"""
Railway / container-friendly config: secrets come from environment variables.
Do not commit real secrets. Locally you can still export the same env vars
or copy config.example.py over this file for a pure-file setup.
"""

from __future__ import annotations

import os
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int = 0) -> int:
    raw = _env(name, "")
    if not raw:
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = _env(name, "")
    if not raw:
        return default
    return float(raw)


def _env_id_list(name: str) -> list[int]:
    raw = _env(name, "")
    if not raw:
        return []
    ids = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part:
            ids.append(int(part))
    return ids


# Data directory resolution (also documented in .env.example and RAILWAY.md):
# 1) ANTI_LOGIN_DATA_ROOT if set (Railway volume recommend: /data)
# 2) else /data when running on Railway and /data is writable
# 3) else the project directory
_PROJECT_DIR = Path(__file__).resolve().parent


def _default_data_root() -> str:
    explicit = os.getenv("ANTI_LOGIN_DATA_ROOT", "").strip()
    if explicit:
        return explicit
    on_railway = bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_PROJECT_ID")
        or os.getenv("RAILWAY_SERVICE_ID")
    )
    if on_railway:
        railway_data = Path("/data")
        try:
            railway_data.mkdir(parents=True, exist_ok=True)
            probe = railway_data / ".anti_login_write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return str(railway_data)
        except OSError:
            pass
    return str(_PROJECT_DIR)


DATA_ROOT = _default_data_root()

API_ID = _env_int("API_ID", 0)
API_HASH = _env("API_HASH", "your_api_hash")
BOT_TOKEN = _env("BOT_TOKEN", "your_bot_token")
ADMIN_IDS = _env_id_list("ADMIN_IDS")

TELETHON_SYNC_WARNING_WINDOW_SECONDS = _env_int(
    "TELETHON_SYNC_WARNING_WINDOW_SECONDS", 1800
)
BOT_LOG_DIR = _env("BOT_LOG_DIR", "logs")
BOT_LOG_RETENTION_DAYS = _env_int("BOT_LOG_RETENTION_DAYS", 30)

SESSIONS_DIR = _env("SESSIONS_DIR", "sessions")
DATA_FILE = _env("DATA_FILE", "user_data.json")
PAYMENT_ORDERS_FILE = _env(
    "PAYMENT_ORDERS_FILE", os.path.join("storage", "payment_orders.json")
)
ADMIN_AUDIT_FILE = _env(
    "ADMIN_AUDIT_FILE", os.path.join("storage", "admin_audit.jsonl")
)
ADMIN_AUDIT_RETENTION_DAYS = _env_int("ADMIN_AUDIT_RETENTION_DAYS", 180)

MERCHANT_ID = _env("MERCHANT_ID", "your_merchant_id")
PAYMENT_TOKEN = _env("PAYMENT_TOKEN", "your_payment_token")
PAYMENT_RETURN_URL = _env("PAYMENT_RETURN_URL", "https://t.me/AntiQin_bot")
PAYMENT_POLL_INTERVAL_SECONDS = _env_float("PAYMENT_POLL_INTERVAL_SECONDS", 5)
PAYMENT_AUTO_CHECK_WINDOW_SECONDS = _env_float(
    "PAYMENT_AUTO_CHECK_WINDOW_SECONDS", 300
)
PAYMENT_ORDER_EXPIRY_SECONDS = _env_float(
    "PAYMENT_ORDER_EXPIRY_SECONDS", 2 * 60 * 60
)
PAYMENT_REQUEST_TIMEOUT_SECONDS = _env_float("PAYMENT_REQUEST_TIMEOUT_SECONDS", 30)
PAYMENT_REQUEST_CONCURRENCY = _env_int("PAYMENT_REQUEST_CONCURRENCY", 2)
PAYMENT_RETRY_BACKOFF_MAX_SECONDS = _env_float(
    "PAYMENT_RETRY_BACKOFF_MAX_SECONDS", 60
)
PAYMENT_PROVIDER_FAILURE_THRESHOLD = _env_int(
    "PAYMENT_PROVIDER_FAILURE_THRESHOLD", 3
)
PAYMENT_PROVIDER_COOLDOWN_SECONDS = _env_float(
    "PAYMENT_PROVIDER_COOLDOWN_SECONDS", 30
)

SESSION_LOAD_CONCURRENCY = _env_int("SESSION_LOAD_CONCURRENCY", 5)
SESSION_RELOAD_CONCURRENCY = _env_int("SESSION_RELOAD_CONCURRENCY", 5)
SESSION_HEALTH_RETRY_ATTEMPTS = _env_int("SESSION_HEALTH_RETRY_ATTEMPTS", 2)
SESSION_HEALTH_RETRY_DELAY_SECONDS = _env_float(
    "SESSION_HEALTH_RETRY_DELAY_SECONDS", 3
)

SESSION_DEVICE_MODEL = _env("SESSION_DEVICE_MODEL", "QinShield")
SESSION_SYSTEM_VERSION = _env("SESSION_SYSTEM_VERSION", "Debian GNU/Linux 12")
SESSION_APP_VERSION = _env("SESSION_APP_VERSION", "12.7")
SESSION_LANG_CODE = _env("SESSION_LANG_CODE", "en")
SESSION_SYSTEM_LANG_CODE = _env("SESSION_SYSTEM_LANG_CODE", "en")

LOGIN_CODE_BACKFILL_WINDOW_SECONDS = _env_int(
    "LOGIN_CODE_BACKFILL_WINDOW_SECONDS", 5 * 60
)
LOGIN_CODE_INVALIDATE_ATTEMPTS = _env_int("LOGIN_CODE_INVALIDATE_ATTEMPTS", 3)
LOGIN_CODE_INVALIDATE_RETRY_DELAYS = (1, 2)
LOGIN_CODE_DEDUP_RETENTION_SECONDS = _env_int(
    "LOGIN_CODE_DEDUP_RETENTION_SECONDS", 10 * 60
)
LOGIN_MONITOR_STATE_FILE = _env(
    "LOGIN_MONITOR_STATE_FILE", os.path.join("storage", "login_monitor_state.json")
)

HOSTED_ACCOUNT_METADATA_FILE = _env(
    "HOSTED_ACCOUNT_METADATA_FILE",
    os.path.join("storage", "hosted_account_metadata.json"),
)
ACCOUNT_TRANSFER_JOURNAL_FILE = _env(
    "ACCOUNT_TRANSFER_JOURNAL_FILE",
    os.path.join("storage", "account_transfer_journal.json"),
)
HOSTING_CLEAN_TIMEOUT_SECONDS = _env_float("HOSTING_CLEAN_TIMEOUT_SECONDS", 120)
HOSTING_CLEAN_MIN_AGE_SECONDS = _env_float("HOSTING_CLEAN_MIN_AGE_SECONDS", 60 * 60)
ACCOUNT_TRANSFER_MIN_AGE_SECONDS = _env_float(
    "ACCOUNT_TRANSFER_MIN_AGE_SECONDS", 24 * 60 * 60
)
HOSTING_OPERATION_MIN_AGE_SECONDS = _env_float(
    "HOSTING_OPERATION_MIN_AGE_SECONDS", 24 * 60 * 60
)
TRANSFER_RECIPIENT_RESTRICTION_SECONDS = _env_float(
    "TRANSFER_RECIPIENT_RESTRICTION_SECONDS", 60 * 60
)

LOGIN_UNLOCK_MONITOR_LIMITS = {"go": 3, "plus": 15, "pro": None}
LOGIN_UNLOCK_RETRY_SECONDS = _env_int("LOGIN_UNLOCK_RETRY_SECONDS", 30)
LOGIN_CODE_REQUEST_MIN_INTERVAL_SECONDS = _env_int(
    "LOGIN_CODE_REQUEST_MIN_INTERVAL_SECONDS", 15
)
LOGIN_CODE_REQUEST_WINDOW_SECONDS = _env_int(
    "LOGIN_CODE_REQUEST_WINDOW_SECONDS", 60 * 60
)
LOGIN_CODE_REQUEST_MAX_PER_WINDOW = _env_int(
    "LOGIN_CODE_REQUEST_MAX_PER_WINDOW", 15
)

# Optional extras used by the modified protection logic.
PROTECTION_BOOST_SECONDS = _env_int("PROTECTION_BOOST_SECONDS", 5 * 60)
AUTH_RECONCILE_MIN_INTERVAL_SECONDS = _env_int(
    "AUTH_RECONCILE_MIN_INTERVAL_SECONDS", 5 * 60
)
RESET_AUTHORIZATION_CONCURRENCY = _env_int("RESET_AUTHORIZATION_CONCURRENCY", 8)
SECURITY_INCIDENT_WINDOW_SECONDS = _env_int(
    "SECURITY_INCIDENT_WINDOW_SECONDS", 10 * 60
)
SECURITY_INCIDENT_THRESHOLD = _env_int("SECURITY_INCIDENT_THRESHOLD", 2)
TOO_NEW_RETRY_SECONDS = _env_int("TOO_NEW_RETRY_SECONDS", 24 * 60 * 60)
