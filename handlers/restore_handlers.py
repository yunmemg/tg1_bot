# Copyright (c) 2026 秦屿泊 (@qinyubo)
# SPDX-License-Identifier: MIT

import logging

from telethon import TelegramClient, events
from telethon.tl.custom import Button

from accounts.account_manager import AccountManager
from handlers.handler_utils import (
    back_button,
    paginate_items,
    pagination_buttons,
    safe_edit,
)
from storage.data_manager import DataManager
from localization import t

logger = logging.getLogger(__name__)


def _language(user_id):
    return DataManager.get_user_language(user_id)


_RESTORE_RESULT_KEYS = {
    "success": "restore.success",
    "already_online": "restore.already_online",
    "no_account": "restore.no_account",
    "no_session": "restore.no_session",
    "session_busy": "restore.session_busy",
    "revoked": "restore.revoked",
    "invalid": "restore.invalid",
}


def _restore_result_text(language: str, result: dict) -> str:
    status = result.get("status") or ("success" if result.get("ok") else "failed")
    key = _RESTORE_RESULT_KEYS.get(status, "restore.failed")
    return t(language, key)


async def setup_restore_handlers(bot: TelegramClient):
    @bot.on(events.CallbackQuery(pattern=rb"restore_menu(?:_\d+)?"))
    async def restore_menu(event):
        """号码恢复：先选择号码，再进行恢复"""
        user_id = event.sender_id
        language = _language(user_id)
        data = event.data.decode(errors="ignore")
        page = int(data.rsplit("_", 1)[1]) if data.startswith("restore_menu_") else 0

        if not AccountManager.check_access(user_id):
            await event.answer(t(language, "common.no_access"), alert=True)
            return

        accounts = AccountManager.get_user_accounts(user_id)

        if not accounts:
            await event.answer()
            await safe_edit(
                event,
                t(language, "restore.empty"),
                buttons=[[back_button(b"back_to_main", user_id=user_id)]],
            )
            return

        account_items, page, max_page = paginate_items(list(accounts.items()), page)
        buttons = []
        for phone, acc_info in account_items:
            display_phone = acc_info.get("display_phone", phone)
            status_text = AccountManager.get_antilogin_status_text(acc_info, user_id)
            buttons.append([
                Button.inline(
                    f"🔄 {display_phone} ｜ {status_text}",
                    data=f"restore_account_{phone}".encode(),
                )
            ])

        if max_page > 0:
            buttons.append(pagination_buttons("restore_menu", page, max_page, language))

        buttons.append([back_button(b"back_to_main", user_id=user_id)])

        await event.answer()
        await safe_edit(
            event,
            t(language, "restore.title", count=len(accounts)),
            buttons=buttons,
        )

    @bot.on(events.CallbackQuery(pattern=rb"restore_account_\+\d+"))
    async def restore_account_callback(event):
        user_id = event.sender_id
        language = _language(user_id)
        phone = event.data.decode().replace("restore_account_", "")

        if not AccountManager.check_access(user_id):
            await event.answer(t(language, "common.no_access"), alert=True)
            return

        await event.answer(t(language, "restore.processing"))
        try:
            result = await AccountManager.restore_account(user_id, phone)
        except Exception as error:
            logger.exception("号码恢复异常: user_id=%s phone=%s", user_id, phone)
            result = {"ok": False, "status": "error"}

        message = _restore_result_text(language, result)
        buttons = [
            [Button.inline(t(language, "restore.back"), b"restore_menu")],
            [back_button(b"back_to_main", user_id=user_id)],
        ]
        await safe_edit(event, message, buttons=buttons)
