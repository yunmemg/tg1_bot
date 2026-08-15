# Copyright (c) 2026 秦屿泊 (@qinyubo)
# SPDX-License-Identifier: MIT

"""R3 签到与邀请：每日签到送临时托管配额，邀请链接送奖励配额。

临时配额写入 user_data 的 ops_bonus 字段，由 DataManager.get_hosting_quota
叠加计算；过期回收由 bot_main 订阅协调任务调用 DataManager.collect_expired_bonus。
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any, Dict, Optional

from telethon import TelegramClient, events
from telethon.tl.custom import Button

from accounts.account_manager import AccountManager
from handlers.handler_utils import back_button, require_access, safe_edit
from localization import t
from storage.data_manager import DataManager, user_data

logger = logging.getLogger(__name__)

CHECKIN_MENU_EMOJI = "✅"
INVITE_MENU_EMOJI = "🎁"

BONUS_KEY = "ops_bonus"


def _language(user_id: int) -> str:
    return DataManager.get_user_language(user_id)


def _checkin_done_today(user_id: int) -> bool:
    info = user_data.get(int(user_id), {})
    bonus = info.get(BONUS_KEY)
    last = bonus.get("last_checkin") if isinstance(bonus, dict) else None
    if not last:
        return False
    return time.strftime("%Y-%m-%d", time.localtime(float(last))) == time.strftime(
        "%Y-%m-%d", time.localtime()
    )


def _sign_invite(inviter_id: int, expires_at: float) -> str:
    import settings as config
    payload = f"{inviter_id}.{int(expires_at)}"
    signature = hmac.new(
        config.BOT_TOKEN.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()[:16]
    return f"{payload}.{signature}"


def verify_invite_token(token: str) -> Optional[Dict[str, Any]]:
    """校验邀请 token，返回 {inviter_id, expires_at}；无效返回 None。"""
    import settings as config
    parts = token.split(".")
    if len(parts) != 3:
        return None
    inviter_raw, expiry_raw, signature = parts
    try:
        inviter_id = int(inviter_raw)
        expires_at = int(expiry_raw)
    except (TypeError, ValueError):
        return None
    if expires_at < time.time():
        return None
    expected = hmac.new(
        config.BOT_TOKEN.encode(),
        f"{inviter_raw}.{expiry_raw}".encode(),
        hashlib.sha256,
    ).hexdigest()[:16]
    if not hmac.compare_digest(expected, signature):
        return None
    return {"inviter_id": inviter_id, "expires_at": expires_at}


def grant_invite_bonus(invitee_id: int, inviter_id: int) -> Optional[Dict[str, Any]]:
    """被邀请人使用链接后，给邀请人发放奖励配额。防重复：同一被邀请人只奖励一次。"""
    import settings as config
    if inviter_id == invitee_id or DataManager.is_admin(inviter_id):
        return None
    info = user_data.setdefault(int(inviter_id), {})
    bonus = info.setdefault(BONUS_KEY, {})
    existing = bonus.setdefault("invites", [])
    if any(int(item.get("invitee", -1)) == int(invitee_id) for item in existing):
        return None
    expires_at = time.time() + config.INVITE_BONUS_HOURS * 3600
    existing.append({
        "quota": config.INVITE_BONUS_QUOTA,
        "expires_at": expires_at,
        "invitee": int(invitee_id),
    })
    if DataManager.save_user_data():
        return {"quota": config.INVITE_BONUS_QUOTA, "expires_at": expires_at}
    return None


async def resolve_invite_payload(bot: TelegramClient, user_id: int, payload: str) -> bool:
    """处理 /start invite_<token>：被邀请人完成奖励流程。

    返回 True 表示该 payload 被本模块消费。
    """
    if not payload.startswith("invite_"):
        return False
    token = payload[len("invite_"):]
    verified = verify_invite_token(token)
    language = _language(user_id)
    if not verified:
        await bot.send_message(user_id, t(language, "ops.invite.invalid"))
        return True
    inviter_id = verified["inviter_id"]
    result = grant_invite_bonus(user_id, inviter_id)
    if result is None:
        await bot.send_message(user_id, t(language, "ops.invite.used"))
    else:
        hours = max(1, int((result["expires_at"] - time.time()) / 3600))
        await bot.send_message(
            user_id,
            t(language, "ops.invite.accepted",
              quota=result["quota"], hours=hours),
        )
        try:
            inviter_lang = _language(inviter_id)
            await bot.send_message(
                inviter_id,
                t(inviter_lang, "ops.invite.reward",
                  quota=result["quota"], invitee=user_id),
            )
        except Exception:
            logger.warning("邀请奖励通知失败: 邀请人=%s", inviter_id)
    return True


def build_invite_link(user_id: int) -> str:
    """生成带签名 token 的邀请链接。"""
    import settings as config
    expires_at = time.time() + 30 * 86400
    token = _sign_invite(user_id, expires_at)
    username = getattr(config, "BOT_USERNAME", "")
    if username:
        return f"https://t.me/{username}?start=invite_{token}"
    return f"https://t.me/{config.BOT_TOKEN.split(':')[0]}?start=invite_{token}"


async def setup_checkin_invite_handlers(bot: TelegramClient) -> None:
    @bot.on(events.CallbackQuery(pattern=b"ops_checkin"))
    async def checkin_menu(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        await event.answer()
        language = _language(user_id)
        import settings as config
        lines = [
            t(language, "ops.checkin.menu"),
            "",
            t(language, "ops.checkin.reward",
              quota=config.CHECKIN_BONUS_QUOTA, hours=config.CHECKIN_BONUS_HOURS),
        ]
        buttons = []
        if _checkin_done_today(user_id):
            lines.append(t(language, "ops.checkin.done"))
            buttons.append([
                Button.inline(t(language, "ops.checkin.claimed"), b"ops_checkin_noop")
            ])
        else:
            buttons.append([
                Button.inline(t(language, "ops.checkin.action"), b"ops_checkin_do")
            ])
        buttons.append([back_button(b"back_to_main", language=language)])
        await safe_edit(event, "\n".join(lines), buttons=buttons)

    @bot.on(events.CallbackQuery(pattern=b"ops_checkin_do"))
    async def checkin_do(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        language = _language(user_id)
        if _checkin_done_today(user_id):
            await event.answer(t(language, "ops.checkin.done"), alert=True)
            return
        import settings as config
        info = user_data.setdefault(int(user_id), {})
        bonus = info.setdefault(BONUS_KEY, {})
        bonus["checkin"] = {
            "quota": config.CHECKIN_BONUS_QUOTA,
            "expires_at": time.time() + config.CHECKIN_BONUS_HOURS * 3600,
        }
        bonus["last_checkin"] = time.time()
        if not DataManager.save_user_data():
            await event.answer(t(language, "ops.checkin.save_failed"), alert=True)
            return
        await event.answer(t(language, "ops.checkin.claimed"), alert=True)
        await safe_edit(
            event,
            t(language, "ops.checkin.success",
              quota=config.CHECKIN_BONUS_QUOTA, hours=config.CHECKIN_BONUS_HOURS),
            buttons=[[back_button(b"ops_checkin", language=language)]],
        )

    @bot.on(events.CallbackQuery(pattern=b"ops_checkin_noop"))
    async def checkin_noop(event):
        await event.answer()

    @bot.on(events.CallbackQuery(pattern=b"ops_invite"))
    async def invite_menu(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        await event.answer()
        language = _language(user_id)
        import settings as config
        link = build_invite_link(user_id)
        lines = [
            t(language, "ops.invite.menu",
              quota=config.INVITE_BONUS_QUOTA, hours=config.INVITE_BONUS_HOURS),
            "",
            link,
        ]
        await safe_edit(
            event,
            "\n".join(lines),
            buttons=[[back_button(b"back_to_main", language=language)]],
        )
