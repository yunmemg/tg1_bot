# Copyright (c) 2026 秦屿泊 (@qinyubo)
# SPDX-License-Identifier: MIT

import os

# All relative runtime paths are resolved below this directory. The default is
# the project directory; set an absolute path to keep state elsewhere.
DATA_ROOT = os.path.dirname(os.path.abspath(__file__))

# Telegram API config
API_ID = 0
API_HASH = "your_api_hash"
BOT_TOKEN = "your_bot_token"

# Actionable Telegram connection warnings are rate-limited per error type.
# This value is read from the TELETHON_SYNC_WARNING_WINDOW_SECONDS environment
# variable at logging startup; 1800 seconds is the default.
TELETHON_SYNC_WARNING_WINDOW_SECONDS = 1800

# Store runtime logs in this directory, split at local midnight, and retain
# this many daily files.
BOT_LOG_DIR = "logs"
BOT_LOG_RETENTION_DAYS = 30

# Admin Telegram user IDs
ADMIN_IDS = []

# Paths
SESSIONS_DIR = "sessions"
DATA_FILE = "user_data.json"
PAYMENT_ORDERS_FILE = os.path.join("storage", "payment_orders.json")
ADMIN_AUDIT_FILE = os.path.join("storage", "admin_audit.jsonl")
ADMIN_AUDIT_RETENTION_DAYS = 180

# OkayPay config
MERCHANT_ID = "your_merchant_id"
PAYMENT_TOKEN = "your_payment_token"
PAYMENT_RETURN_URL = "https://t.me/AntiQin_bot"
PAYMENT_POLL_INTERVAL_SECONDS = 5
PAYMENT_AUTO_CHECK_WINDOW_SECONDS = 300
PAYMENT_ORDER_EXPIRY_SECONDS = 2 * 60 * 60
PAYMENT_REQUEST_TIMEOUT_SECONDS = 30
PAYMENT_REQUEST_CONCURRENCY = 2
PAYMENT_RETRY_BACKOFF_MAX_SECONDS = 60
PAYMENT_PROVIDER_FAILURE_THRESHOLD = 3
PAYMENT_PROVIDER_COOLDOWN_SECONDS = 30

# Startup session loading concurrency
SESSION_LOAD_CONCURRENCY = 5
SESSION_RELOAD_CONCURRENCY = 5
SESSION_HEALTH_RETRY_ATTEMPTS = 2
SESSION_HEALTH_RETRY_DELAY_SECONDS = 3

# Global session parameters
SESSION_DEVICE_MODEL = "QinShield"
SESSION_SYSTEM_VERSION = "Debian GNU/Linux 12"
SESSION_APP_VERSION = "12.7"
SESSION_LANG_CODE = "en"
SESSION_SYSTEM_LANG_CODE = "en"

# Login code monitoring
LOGIN_CODE_BACKFILL_WINDOW_SECONDS = 5 * 60
LOGIN_CODE_INVALIDATE_ATTEMPTS = 3
LOGIN_CODE_INVALIDATE_RETRY_DELAYS = (1, 2)
LOGIN_CODE_DEDUP_RETENTION_SECONDS = 10 * 60
LOGIN_MONITOR_STATE_FILE = os.path.join("storage", "login_monitor_state.json")

# Hosted account metadata and transfers
HOSTED_ACCOUNT_METADATA_FILE = os.path.join("storage", "hosted_account_metadata.json")
ACCOUNT_TRANSFER_JOURNAL_FILE = os.path.join("storage", "account_transfer_journal.json")
HOSTING_CLEAN_TIMEOUT_SECONDS = 120
HOSTING_CLEAN_MIN_AGE_SECONDS = 60 * 60
ACCOUNT_TRANSFER_MIN_AGE_SECONDS = 24 * 60 * 60
HOSTING_OPERATION_MIN_AGE_SECONDS = 24 * 60 * 60
TRANSFER_RECIPIENT_RESTRICTION_SECONDS = 60 * 60

# Login unlock reminders. These limits are independent from hosted seats.
LOGIN_UNLOCK_MONITOR_LIMITS = {"go": 3, "plus": 15, "pro": None}
LOGIN_UNLOCK_RETRY_SECONDS = 30
LOGIN_CODE_REQUEST_MIN_INTERVAL_SECONDS = 15
LOGIN_CODE_REQUEST_WINDOW_SECONDS = 60 * 60
LOGIN_CODE_REQUEST_MAX_PER_WINDOW = 15
