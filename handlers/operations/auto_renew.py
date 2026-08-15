# Copyright (c) 2026 秦屿泊 (@qinyubo)
# SPDX-License-Identifier: MIT

"""R6d 自动续费：到期前自动为开启开关的用户生成续费支付订单。

开关存 user_data[uid]["auto_renew"]；后台任务周期性扫描临近到期的订阅，
调用 payment_system.create_subscription_payment 生成续费订单并推送支付链接。
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from telethon import TelegramClient, events
from telethon.tl.custom import Button

from accounts.account_manager import AccountManager
from handlers.handler_utils import back_button, require_access, safe_edit
from localization import t
from storage.data_manager import DataManager, user_data

if TYPE_CHECKING:
    from payments.payment_system import PaymentSystem

logger = logging.getLogger(__name__)

AUTO_RENEW_EMOJI = "🔁"

# 到期前多少天触发续费订单
AUTO_RENEW_LEAD_DAYS = 7
# 每个用户同一订阅窗口只生成一次续费订单
RENEW_ORDER_KEY = "ops_auto_renew_order"

_monitor_task: Optional[asyncio.Task] = None


def _language(user_id: int) -> str:
    return DataManager.get_user_language(user_id)


def is_auto_renew_enabled(user_id: int) -> bool:
    info = user_data.get(int(user_id), {})
    return bool(info.get("auto_renew", False))


def set_auto_renew(user_id: int, enabled: bool) -> bool:
    info = user_data.setdefault(int(user_id), {})
    if bool(info.get("auto_renew", False)) == enabled:
        return True
    info["auto_renew"] = bool(enabled)
    if not enabled:
        info.pop(RENEW_ORDER_KEY, None)
    return DataManager.save_user_data()


def _expires_at_timestamp(subscription: dict) -> Optional[float]:
    try:
        return datetime.fromisoformat(subscription["expires_at"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return None


def _renew_order_snapshot(user_id: int) -> dict:
    info = user_data.get(int(user_id), {})
    return info.get(RENEW_ORDER_KEY) or {}


async def _should_renew(subscription: dict, user_id: int) -> bool:
    """是否需要在当前窗口为该订阅生成续费订单。"""
    expires = _expires_at_timestamp(subscription)
    if expires is None:
        return False
    now = time.time()
    lead = AUTO_RENEW_LEAD_DAYS * 86400
    if not (now <= expires <= now + lead):
        return False
    snapshot = _renew_order_snapshot(user_id)
    if snapshot.get("expires_at") == subscription.get("expires_at"):
        return False
    return True


async def _trigger_renewal(bot, payment_system: "PaymentSystem", user_id: int, subscription: dict) -> None:
    language = _language(user_id)
    plan_id = subscription.get("plan_id", "go")
    quota = subscription.get("quota")
    if quota is None or plan_id == "pro":
        return
    try:
        result = await payment_system.create_subscription_payment(
            user_id, plan_id, quota, period_days=30
        )
    except Exception:
        logger.exception("自动续费订单生成异常: 用户ID=%s", user_id)
        return
    if not result.get("success"):
        logger.info("自动续费订单未生成: 用户ID=%s, 原因=%s", user_id, result.get("error"))
        return
    info = user_data.setdefault(int(user_id), {})
    info[RENEW_ORDER_KEY] = {
        "expires_at": subscription.get("expires_at"),
        "order_created_at": time.time(),
    }
    DataManager.save_user_data()
    pay_url = result.get("pay_url") or result.get("url")
    try:
        text = (
            t(language, "ops.auto_renew.order_created",
              plan=plan_id, quota=quota, link=pay_url)
            if pay_url
            else t(language, "ops.auto_renew.order_created_no_link", plan=plan_id)
        )
        await AccountManager._safe_send_bot_message(
            bot, user_id, text, context=f"auto_renew:{plan_id}",
        )
    except Exception:
        logger.exception("自动续费订单推送失败: 用户ID=%s", user_id)


async def _auto_renew_loop(bot, payment_system: "PaymentSystem") -> None:
    while True:
        try:
            await _auto_renew_once(bot, payment_system)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("自动续费扫描异常")
        await asyncio.sleep(6 * 3600)


async def _auto_renew_once(bot, payment_system: "PaymentSystem") -> None:
    for user_id in DataManager.get_subscription_user_ids():
        if not is_auto_renew_enabled(user_id):
            continue
        subscription = DataManager.get_subscription(user_id)
        if not subscription:
            continue
        if await _should_renew(subscription, user_id):
            await _trigger_renewal(bot, payment_system, user_id, subscription)


def start_auto_renew_monitor(bot, payment_system: "PaymentSystem") -> Optional[asyncio.Task]:
    global _monitor_task
    if _monitor_task and not _monitor_task.done():
        return _monitor_task
    _monitor_task = asyncio.create_task(_auto_renew_loop(bot, payment_system))
    return _monitor_task


def stop_auto_renew_monitor() -> None:
    global _monitor_task
    task = _monitor_task
    _monitor_task = None
    if task:
        task.cancel()


async def setup_auto_renew_handlers(bot: TelegramClient, payment_system: "PaymentSystem") -> None:
    @bot.on(events.CallbackQuery(pattern=b"ops_auto_renew"))
    async def auto_renew_menu(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        await event.answer()
        language = _language(user_id)
        enabled = is_auto_renew_enabled(user_id)
        buttons = [
            [
                Button.inline(
                    t(language, "ops.auto_renew.on" if not enabled else "ops.auto_renew.disable"),
                    b"ops_auto_renew_toggle",
                )
            ],
            [back_button(b"back_to_main", language=language)],
        ]
        status_text = (
            t(language, "ops.auto_renew.on_status")
            if enabled
            else t(language, "ops.auto_renew.off_status")
        )
        await safe_edit(
            event,
            t(language, "ops.auto_renew.menu", lead=AUTO_RENEW_LEAD_DAYS) + "\n\n" + status_text,
            buttons=buttons,
        )

    @bot.on(events.CallbackQuery(pattern=b"ops_auto_renew_toggle"))
    async def auto_renew_toggle(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        language = _language(user_id)
        enabled = is_auto_renew_enabled(user_id)
        if not set_auto_renew(user_id, not enabled):
            await event.answer(t(language, "ops.auto_renew.save_failed"), alert=True)
            return
        await event.answer(t(language, "ops.auto_renew.updated"), alert=True)
        await auto_renew_menu(event)
