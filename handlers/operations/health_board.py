# Copyright (c) 2026 秦屿泊 (@qinyubo)
# SPDX-License-Identifier: MIT

"""R5 健康看板：实时推导托管账号健康状态，无持久化。"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from telethon import TelegramClient, events
from telethon.tl.custom import Button

from accounts.account_manager import AccountManager
from handlers.handler_utils import back_button, paginate_items, pagination_buttons, require_access, safe_edit
from localization import t
from storage.data_manager import DataManager

logger = logging.getLogger(__name__)

HEALTH_BOARD_EMOJI = "📊"


def _language(user_id: int) -> str:
    return DataManager.get_user_language(user_id)


def _account_health(acc_info: Dict) -> str:
    """返回 online / frozen / offline。"""
    if not acc_info:
        return "offline"
    if not AccountManager.is_account_online(acc_info):
        return "offline"
    health = (acc_info.get("health_status") or "alive").lower()
    if health == "frozen":
        return "frozen"
    return "online"


def build_health_snapshot(user_id: int) -> Dict:
    """汇总用户全部托管账号的健康状态。"""
    accounts = AccountManager.get_user_accounts(user_id) or {}
    snapshot = {"total": 0, "online": 0, "frozen": 0, "offline": 0, "items": []}
    for phone, acc_info in accounts.items():
        status = _account_health(acc_info)
        snapshot[status] += 1
        snapshot["total"] += 1
        snapshot["items"].append({
            "phone": phone,
            "display": AccountManager.format_phone_display(phone),
            "status": status,
            "mode": AccountManager.get_account_mode(acc_info),
            "anti_login": bool(acc_info.get("anti_login", True)),
            "last_reload": acc_info.get("last_reload"),
        })
    snapshot["items"].sort(key=lambda item: item["phone"])
    return snapshot


def _mode_text(mode: str, language: str) -> str:
    if mode == "pause":
        return t(language, "ops.health.mode.pause")
    if mode == "code_fetch":
        return t(language, "ops.health.mode.code_fetch")
    return t(language, "ops.health.mode.normal")


def render_snapshot(snapshot: Dict, page: int, language: str) -> str:
    lines = [
        t(language, "ops.health.summary",
          total=snapshot["total"], online=snapshot["online"],
          frozen=snapshot["frozen"], offline=snapshot["offline"]),
        "",
    ]
    items = snapshot["items"]
    page_items, _, max_page = paginate_items(items, page, page_size=8)
    for item in page_items:
        status_text = t(language, "ops.health.status." + item["status"])
        mode_text = _mode_text(item["mode"], language)
        lines.append(f"{status_text} · {item['display']} · {mode_text}")
    if not items:
        lines.append(t(language, "ops.health.empty"))
    return "\n".join(lines)


async def setup_health_board_handlers(bot: TelegramClient) -> None:
    @bot.on(events.CallbackQuery(pattern=rb"ops_health(?:_(\d+))?"))
    async def health_board(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        await event.answer()
        language = _language(user_id)
        match = event.pattern_match
        page = int(match.group(1)) if match and match.group(1) else 0
        snapshot = build_health_snapshot(user_id)
        text = render_snapshot(snapshot, page, language)
        buttons = []
        page_items, current_page, max_page = paginate_items(snapshot["items"], page, page_size=8)
        if max_page > 0:
            buttons.append(pagination_buttons("ops_health", current_page, max_page, language))
        buttons.append([back_button(b"back_to_main", language=language)])
        await safe_edit(event, text, buttons=buttons)
