# Copyright (c) 2026 秦屿泊 (@qinyubo)
# SPDX-License-Identifier: MIT

"""R4 解限自动登录：受限号码解限后自动检测并引导完成登录。

设计要点：
- 受限号码（FloodWait）无法配置托管，只能等解限后登录
- 解限时刻由 LoginUnlockReminderSystem.unlock_attained_callback 触发
- 到达后自动调用 AccountManager.authenticate（send_code_request 发验证码到手机）
- 推送"输入验证码"按钮，用户回填验证码复用 account_handlers 的 waiting_code 流程
- 登录成功由 promote_pending_client 自动配置反登录（anti_login=True）
- 若号码仍受限，authenticate 内部会重新 schedule 解限提醒，不打扰
"""

from __future__ import annotations

import asyncio
import logging

from telethon import TelegramClient, events
from telethon.tl.custom import Button

from accounts import account_runtime
from accounts.account_manager import AccountManager
from accounts.login_code_rate_limiter import (
    LoginCodeRateLimitMessage,
    login_code_request_rate_limiter,
)
from handlers.account_handlers import cancel_pending_login_flow
from handlers.handler_utils import back_button, get_state, require_access
from localization import t
from reminders.login_unlock_reminder import phone_key
from storage.data_manager import DataManager

logger = logging.getLogger(__name__)

RELOGIN_MENU_EMOJI = "🔄"

# 每个用户同一号码同时只允许一个自动登录流程
_inflight: set = set()


def _language(user_id: int) -> str:
    return DataManager.get_user_language(user_id)


async def _notify(user_id: int, text: str, context: str, buttons=None) -> bool:
    bot = account_runtime.get_notify_bot()
    if not bot:
        return False
    try:
        return bool(await AccountManager._safe_send_bot_message(
            bot, user_id, text, context=context,
        ))
    except account_runtime.NotifyBotFatalError:
        raise
    except Exception:
        logger.exception("解限自动登录通知失败: 用户ID=%s", user_id)
        return False


async def _start_auto_login(user_id: int, phone: str) -> None:
    """解限时刻自动发起登录：send_code_request 发验证码，推送输入验证码按钮。"""
    language = _language(user_id)
    normalized = AccountManager.normalize_phone(phone)
    inflight_key = f"{int(user_id)}_{normalized}"

    if not AccountManager.check_access(user_id):
        return
    if inflight_key in _inflight:
        return
    cleanup = await cancel_pending_login_flow(
        user_id, reason="auto_relogin", preserve_message=None
    )
    if not cleanup.ok:
        return

    rate_limit = login_code_request_rate_limiter.acquire(user_id)
    if not rate_limit.allowed:
        return

    _inflight.add(inflight_key)
    try:
        client = await AccountManager.create_new_client(phone, user_id)
        result = await AccountManager.authenticate(client, phone, user_id)
    except account_runtime.NotifyBotFatalError:
        raise
    except Exception:
        logger.exception("解限自动登录异常: 用户ID=%s, 手机号=%s", user_id, phone)
        return
    finally:
        _inflight.discard(inflight_key)

    state = get_state(user_id)
    if not (state and state.get("waiting_code")):
        if isinstance(result, LoginCodeRateLimitMessage):
            return
        # 号码仍受限或发码失败：authenticate 内部已重新 schedule，不打扰。
        return

    buttons = [
        [Button.inline(
            t(language, "ops.relogin.code_button"),
            f"ops_relogin_code_{phone_key(normalized)}".encode(),
        )],
        [back_button(b"back_to_main", language=language)],
    ]
    await _notify(
        user_id,
        t(
            language,
            "ops.relogin.unlock_notify",
            phone=AccountManager.format_phone_display(phone),
        ),
        f"auto_relogin:{normalized}",
        buttons=buttons,
    )


async def _on_unlock_attained(user_id: int, phone: str) -> None:
    """LoginUnlockReminderSystem 解限时刻回调入口。"""
    try:
        await _start_auto_login(user_id, phone)
    except account_runtime.NotifyBotFatalError:
        raise
    except Exception:
        logger.exception("解限自动登录回调异常: 用户ID=%s, 手机号=%s", user_id, phone)


def install(bot: TelegramClient) -> None:
    """把自动登录钩子挂到解限提醒系统。"""
    system = account_runtime.get_login_unlock_reminder_system()
    if system is None:
        logger.warning("解限提醒系统尚未就绪，自动登录钩子未安装")
        return
    system.unlock_attained_callback = _on_unlock_attained
    logger.info("✅ 解限自动登录钩子已安装")


async def setup_auto_relogin(bot: TelegramClient) -> None:
    install(bot)

    @bot.on(events.CallbackQuery(pattern=rb"^ops_relogin_code_\d+$"))
    async def relogin_code_button(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        await event.answer()
        language = _language(user_id)
        state = get_state(user_id)
        if not (state and state.get("waiting_code")):
            await event.respond(
                t(language, "ops.relogin.flow_expired"),
                buttons=[[back_button(b"back_to_main", language=language)]],
            )
            return
        await event.respond(
            t(language, "ops.relogin.code_prompt"),
            buttons=[[back_button(b"back_to_main", language=language)]],
        )
