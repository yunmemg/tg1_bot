# Copyright (c) 2026 秦屿泊 (@qinyubo)
# SPDX-License-Identifier: MIT

"""R6b 卡密系统：管理员批量生成卡密，用户兑换订阅。

卡密存 system_settings.redeem_codes；核销在单线程持锁内完成
used=True + 持久化后才发放订阅，保证一次性。
"""

from __future__ import annotations

import logging
import secrets
import string
import time
from typing import Dict, List, Optional

from telethon import TelegramClient, events
from telethon.tl.custom import Button

from handlers.handler_utils import back_button, require_access, require_admin, safe_edit
from localization import t
from storage.data_manager import DataManager

logger = logging.getLogger(__name__)

REDEEM_EMOJI = "🎟️"

_code_alphabet = string.ascii_uppercase + string.digits


def _language(user_id: int) -> str:
    return DataManager.get_user_language(user_id)


def _codes() -> Dict[str, Dict]:
    from storage.data_manager import user_data
    settings = user_data.get("system_settings") or {}
    codes = settings.get("redeem_codes")
    if not isinstance(codes, dict):
        return {}
    return codes


def _save_codes(codes: Dict[str, Dict]) -> bool:
    from storage.data_manager import user_data
    settings = user_data.setdefault("system_settings", {})
    settings["redeem_codes"] = codes
    return DataManager.save_user_data()


def generate_codes(plan_id: str, days: int, count: int, quota: Optional[int] = None) -> List[str]:
    """批量生成卡密，返回新卡密列表。"""
    import settings as config
    length = config.REDEEM_CODE_LENGTH
    existing = _codes()
    created: List[str] = []
    for _ in range(max(1, int(count))):
        while True:
            raw = "".join(secrets.choice(_code_alphabet) for _ in range(length))
            code = "-".join(raw[i:i + 4] for i in range(0, length, 4))
            if code not in existing:
                break
        existing[code] = {
            "plan_id": plan_id,
            "quota": quota,
            "days": int(days),
            "used": False,
            "used_by": None,
            "created_at": time.time(),
        }
        created.append(code)
    if _save_codes(existing):
        return created
    return []


def redeem_code(user_id: int, code: str) -> str:
    """核销卡密并发放订阅。返回本地化提示文本。"""
    language = _language(user_id)
    normalized = code.strip().upper()
    codes = _codes()
    entry = codes.get(normalized)
    if not entry:
        return t(language, "ops.redeem.invalid")
    if entry.get("used"):
        return t(language, "ops.redeem.used")
    plan_id = entry.get("plan_id", "go")
    days = int(entry.get("days", 30))
    quota = entry.get("quota")
    if quota is None and plan_id != "pro":
        catalog = DataManager.get_subscription_catalog().get(plan_id, {})
        quota = catalog.get("quota")
    # 先标记 + 持久化，成功后才发订阅，保证一次性
    entry["used"] = True
    entry["used_by"] = int(user_id)
    entry["used_at"] = time.time()
    if not _save_codes(codes):
        return t(language, "ops.redeem.save_failed")
    if not DataManager.apply_subscription(
        user_id, plan_id, quota, days=days, validate_catalog=False,
        billing_price=None, order_id=f"redeem-{normalized}",
    ):
        entry["used"] = False
        entry["used_by"] = None
        entry.pop("used_at", None)
        _save_codes(codes)
        return t(language, "ops.redeem.apply_failed")
    return t(language, "ops.redeem.success",
             plan=plan_id, days=days, code=normalized)


async def setup_redeem_handlers(bot: TelegramClient) -> None:
    @bot.on(events.CallbackQuery(pattern=b"ops_redeem"))
    async def redeem_menu(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        await event.answer()
        language = _language(user_id)
        await safe_edit(
            event,
            t(language, "ops.redeem.menu"),
            buttons=[[Button.inline(t(language, "ops.redeem.enter"), b"ops_redeem_enter")],
                     [back_button(b"back_to_main", language=language)]],
        )

    @bot.on(events.CallbackQuery(pattern=b"ops_redeem_enter"))
    async def redeem_enter(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        await event.answer()
        language = _language(user_id)
        from handlers.handler_utils import set_state
        set_state(user_id, **{"ops_redeem_waiting": True})
        await safe_edit(
            event,
            t(language, "ops.redeem.prompt"),
            buttons=[[back_button(b"ops_redeem", language=language)]],
        )

    @bot.on(events.CallbackQuery(pattern=b"ops_redeem_admin"))
    async def redeem_admin(event):
        if not await require_admin(event, alert=True):
            return
        await event.answer()
        language = _language(event.sender_id)
        catalog = DataManager.get_subscription_catalog()
        buttons = [
            [Button.inline(plan["name"], f"ops_redeem_gen_{pid}".encode())]
            for pid, plan in catalog.items()
        ]
        buttons.append([back_button(b"back_to_main", language=language)])
        await safe_edit(event, t(language, "ops.redeem.admin_menu"), buttons=buttons)

    @bot.on(events.CallbackQuery(pattern=rb"ops_redeem_gen_(\w+)"))
    async def redeem_generate(event):
        if not await require_admin(event, alert=True):
            return
        plan_id = event.pattern_match.group(1).decode()
        from handlers.handler_utils import set_state
        set_state(event.sender_id, **{"ops_redeem_plan": plan_id})
        await event.answer()
        language = _language(event.sender_id)
        await safe_edit(
            event,
            t(language, "ops.redeem.gen_prompt"),
            buttons=[[back_button(b"back_to_main", language=language)]],
        )

    @bot.on(events.NewMessage(func=lambda e: e.is_private))
    async def redeem_text_capture(event):
        user_id = event.sender_id
        if not event.raw_text:
            return
        from handlers.handler_utils import clear_state, get_state
        state = get_state(user_id)
        plan_id = state.get("ops_redeem_plan")
        text = event.raw_text.strip()
        if plan_id:
            # 管理员生成卡密：格式 "数量 天数" 或 "数量 天数 配额"
            try:
                parts = text.split()
                if len(parts) == 2:
                    count, days = int(parts[0]), int(parts[1])
                    quota = None
                elif len(parts) == 3:
                    count, days, quota = int(parts[0]), int(parts[1]), int(parts[2])
                else:
                    raise ValueError
                if count <= 0 or count > 200 or days <= 0 or days > 3650:
                    raise ValueError
            except ValueError:
                language = _language(user_id)
                await event.respond(t(language, "ops.redeem.gen_invalid"))
                return
            clear_state(user_id, "ops_redeem_plan")
            language = _language(user_id)
            codes = generate_codes(plan_id, days, count, quota)
            if not codes:
                await event.respond(t(language, "ops.redeem.gen_failed"))
                return
            await event.respond(
                t(language, "ops.redeem.generated", count=len(codes), plan=plan_id, days=days)
                + "\n\n" + "\n".join(f"`{c}`" for c in codes),
                parse_mode="md",
            )
            return
        if state.get("ops_redeem_waiting") and AccountManager_check_access(user_id):
            clear_state(user_id, "ops_redeem_waiting")
            result = redeem_code(user_id, text)
            await event.respond(result)


def AccountManager_check_access(user_id: int) -> bool:
    from accounts.account_manager import AccountManager
    return AccountManager.check_access(user_id)
