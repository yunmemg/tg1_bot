# Copyright (c) 2026 秦屿泊 (@qinyubo)
# SPDX-License-Identifier: MIT

"""R6c 批量操作：一键暂停/恢复/删除全部托管账号。

复用 AccountManager 现有接口，循环调度执行，带确认与结果汇总。
"""

from __future__ import annotations

import logging
from typing import Dict, List

from telethon import TelegramClient, events
from telethon.tl.custom import Button

from accounts.account_manager import AccountManager
from handlers.handler_utils import back_button, require_access, safe_edit
from localization import t
from storage.data_manager import DataManager

logger = logging.getLogger(__name__)

BATCH_OPS_EMOJI = "⚡"


def _language(user_id: int) -> str:
    return DataManager.get_user_language(user_id)


def _batch_targets(user_id: int) -> List[str]:
    """返回用户全部托管账号（含 session 文件）。"""
    phones = sorted(AccountManager.hosted_account_phones(user_id))
    return phones


async def _confirm_edit(event, text: str, confirm_data: bytes, language: str):
    await safe_edit(
        event,
        text,
        buttons=[
            [Button.inline(t(language, "ops.batch.confirm"), confirm_data)],
            [Button.inline(t(language, "common.cancel"), b"ops_batch_cancel")],
        ],
    )


async def setup_batch_ops_handlers(bot: TelegramClient) -> None:
    @bot.on(events.CallbackQuery(pattern=b"ops_batch"))
    async def batch_menu(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        await event.answer()
        language = _language(user_id)
        count = len(_batch_targets(user_id))
        buttons = [
            [
                Button.inline(t(language, "ops.batch.pause_all"), b"ops_batch_pause"),
                Button.inline(t(language, "ops.batch.resume_all"), b"ops_batch_resume"),
            ],
            [Button.inline(t(language, "ops.batch.delete_all"), b"ops_batch_delete")],
            [back_button(b"back_to_main", language=language)],
        ]
        await safe_edit(
            event,
            t(language, "ops.batch.menu", count=count),
            buttons=buttons,
        )

    @bot.on(events.CallbackQuery(pattern=b"ops_batch_cancel"))
    async def batch_cancel(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        await event.answer()
        language = _language(user_id)
        count = len(_batch_targets(user_id))
        buttons = [
            [
                Button.inline(t(language, "ops.batch.pause_all"), b"ops_batch_pause"),
                Button.inline(t(language, "ops.batch.resume_all"), b"ops_batch_resume"),
            ],
            [Button.inline(t(language, "ops.batch.delete_all"), b"ops_batch_delete")],
            [back_button(b"back_to_main", language=language)],
        ]
        await safe_edit(
            event,
            t(language, "ops.batch.menu", count=count),
            buttons=buttons,
        )

    @bot.on(events.CallbackQuery(pattern=b"ops_batch_pause"))
    async def batch_pause(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        await event.answer()
        language = _language(user_id)
        await _confirm_edit(
            event,
            t(language, "ops.batch.pause_confirm"),
            b"ops_batch_pause_go",
            language,
        )

    @bot.on(events.CallbackQuery(pattern=b"ops_batch_pause_go"))
    async def batch_pause_go(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        language = _language(user_id)
        count = len(_batch_targets(user_id))
        suspended = await AccountManager.suspend_user_accounts(user_id)
        await event.answer(t(language, "ops.batch.done"), alert=True)
        await safe_edit(
            event,
            t(language, "ops.batch.pause_done", suspended=suspended, total=count),
            buttons=[[back_button(b"ops_batch", language=language)]],
        )

    @bot.on(events.CallbackQuery(pattern=b"ops_batch_resume"))
    async def batch_resume(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        await event.answer()
        language = _language(user_id)
        await _confirm_edit(
            event,
            t(language, "ops.batch.resume_confirm"),
            b"ops_batch_resume_go",
            language,
        )

    @bot.on(events.CallbackQuery(pattern=b"ops_batch_resume_go"))
    async def batch_resume_go(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        language = _language(user_id)
        resumed = await AccountManager.resume_selected_accounts(user_id)
        await event.answer(t(language, "ops.batch.done"), alert=True)
        await safe_edit(
            event,
            t(language, "ops.batch.resume_done", resumed=resumed),
            buttons=[[back_button(b"ops_batch", language=language)]],
        )

    @bot.on(events.CallbackQuery(pattern=b"ops_batch_delete"))
    async def batch_delete(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        await event.answer()
        language = _language(user_id)
        await _confirm_edit(
            event,
            t(language, "ops.batch.delete_confirm"),
            b"ops_batch_delete_go",
            language,
        )

    @bot.on(events.CallbackQuery(pattern=b"ops_batch_delete_go"))
    async def batch_delete_go(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        language = _language(user_id)
        ok, fail = 0, 0
        no_account_text = t(language, "protection.no_account")
        for digits in _batch_targets(user_id):
            phone = f"+{digits}"
            result = await AccountManager.delete_account(user_id, phone)
            if result == no_account_text:
                continue
            ok += 1
        await event.answer(t(language, "ops.batch.done"), alert=True)
        await safe_edit(
            event,
            t(language, "ops.batch.delete_done", ok=ok, fail=fail),
            buttons=[[back_button(b"ops_batch", language=language)]],
        )
