# Copyright (c) 2026 秦屿泊 (@qinyubo)
# SPDX-License-Identifier: MIT

"""R2 工单系统：双向对话式，用户提交 + 管理员回复 + 关闭/重开。"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from telethon import TelegramClient, events
from telethon.tl.custom import Button

from accounts import account_runtime
from accounts.account_manager import AccountManager
from handlers.handler_utils import (
    back_button,
    clear_state,
    get_state,
    paginate_items,
    pagination_buttons,
    require_access,
    require_admin,
    safe_edit,
    set_state,
)
from handlers.operations import ops_store
from localization import t
from storage.data_manager import DataManager

logger = logging.getLogger(__name__)

TICKET_MENU_EMOJI = "🎫"
_TICKET_DRAFT_KEY = "ops_ticket_draft"
_TICKET_CATEGORY_KEY = "ops_ticket_category"
_TICKET_VIEW_KEY = "ops_ticket_view"

CATEGORIES = ("account", "payment", "login", "other")


def _language(user_id: int) -> str:
    return DataManager.get_user_language(user_id)


async def _notify_admins_about_ticket(bot: TelegramClient, ticket: Dict, message: str) -> None:
    for admin_id in _config_admin_ids():
        try:
            await bot.send_message(admin_id, message)
        except Exception:
            logger.warning("工单通知管理员失败: 管理员=%s", admin_id)


def _config_admin_ids() -> List[int]:
    import settings as config
    return config.ADMIN_IDS


async def setup_ticket_handlers(bot: TelegramClient) -> None:
    @bot.on(events.CallbackQuery(pattern=b"ops_ticket_menu"))
    async def ticket_menu(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        await event.answer()
        language = _language(user_id)
        buttons = [
            [Button.inline(t(language, "ops.ticket.create"), b"ops_tk_new")],
            [Button.inline(t(language, "ops.ticket.my_list"), b"ops_tk_mine")],
            [back_button(b"back_to_main", language=language)],
        ]
        if DataManager.is_admin(user_id):
            buttons.insert(0, [
                Button.inline(t(language, "ops.ticket.inbox"), b"ops_tk_inbox")
            ])
        await safe_edit(event, t(language, "ops.ticket.menu"), buttons=buttons)

    @bot.on(events.CallbackQuery(pattern=b"ops_tk_new"))
    async def ticket_new(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        await event.answer()
        language = _language(user_id)
        buttons = []
        for cat in CATEGORIES:
            buttons.append([Button.inline(
                t(language, f"ops.ticket.cat.{cat}"), f"ops_tk_cat_{cat}".encode()
            )])
        buttons.append([back_button(b"ops_ticket_menu", language=language)])
        await safe_edit(event, t(language, "ops.ticket.choose_category"), buttons=buttons)

    @bot.on(events.CallbackQuery(pattern=rb"ops_tk_cat_\w+"))
    async def ticket_category(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        category = event.data.decode().replace("ops_tk_cat_", "")
        set_state(user_id, **{_TICKET_CATEGORY_KEY: category})
        await event.answer()
        language = _language(user_id)
        await safe_edit(
            event,
            t(language, "ops.ticket.describe"),
            buttons=[[back_button(b"ops_tk_new", language=language)]],
        )

    @bot.on(events.NewMessage(func=lambda e: e.is_private))
    async def ticket_text_capture(event):
        user_id = event.sender_id
        if not AccountManager.check_access(user_id):
            return
        state = get_state(user_id)
        if state.get(_TICKET_DRAFT_KEY):
            return
        category = state.get(_TICKET_CATEGORY_KEY)
        if not category or not event.raw_text:
            return
        clear_state(user_id, _TICKET_CATEGORY_KEY)
        text = event.raw_text.strip()
        ticket_id = ops_store.next_ticket_id()
        now = time.time()
        existing_open = [tk for tk in ops_store.tickets_for_user(user_id) if tk.get("status") == "open"]
        if existing_open:
            ticket = existing_open[0]
            ticket["messages"].append({
                "role": "user", "text": text, "ts": now,
            })
            ticket["updated_at"] = now
            ops_store.upsert_ticket(ticket)
            message = f"#{ticket['id']} 用户追加消息: {text[:100]}"
        else:
            ticket = {
                "id": ticket_id,
                "user_id": user_id,
                "category": category,
                "status": "open",
                "created_at": now,
                "updated_at": now,
                "messages": [{"role": "user", "text": text, "ts": now}],
            }
            ops_store.upsert_ticket(ticket)
            message = f"新工单 #{ticket_id} ({category}) 用户ID={user_id}: {text[:100]}"
        _notify_admins_about_ticket(bot, ticket, message)
        await event.respond(
            t(_language(user_id), "ops.ticket.created", ticket_id=ticket["id"]),
            buttons=[[back_button(b"ops_ticket_menu", language=_language(user_id))]],
        )

    @bot.on(events.CallbackQuery(pattern=b"ops_tk_mine"))
    async def ticket_mine(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        await event.answer()
        language = _language(user_id)
        tickets = ops_store.tickets_for_user(user_id)
        if not tickets:
            await safe_edit(
                event,
                t(language, "ops.ticket.empty"),
                buttons=[[back_button(b"ops_ticket_menu", language=language)]],
            )
            return
        buttons = []
        for tk in tickets[:10]:
            status = t(language, "ops.ticket.status.open") if tk.get("status") == "open" else t(language, "ops.ticket.status.closed")
            buttons.append([Button.inline(
                f"#{tk['id']} · {status}", f"ops_tk_view_user_{tk['id']}".encode()
            )])
        buttons.append([back_button(b"ops_ticket_menu", language=language)])
        await safe_edit(event, t(language, "ops.ticket.my_list"), buttons=buttons)

    @bot.on(events.CallbackQuery(pattern=b"ops_tk_inbox"))
    async def ticket_inbox(event):
        user_id = event.sender_id
        if not await require_admin(event, alert=True):
            return
        await event.answer()
        language = _language(user_id)
        all_tickets = ops_store.list_all_tickets()
        open_tickets = [tk for tk in all_tickets if tk.get("status") == "open"]
        if not open_tickets:
            await safe_edit(
                event,
                t(language, "ops.ticket.inbox_empty"),
                buttons=[[back_button(b"ops_ticket_menu", language=language)]],
            )
            return
        buttons = []
        for tk in open_tickets[:15]:
            buttons.append([Button.inline(
                f"#{tk['id']} · U{tk['user_id']} · {tk.get('category')}",
                f"ops_tk_view_admin_{tk['id']}".encode(),
            )])
        buttons.append([back_button(b"ops_ticket_menu", language=language)])
        await safe_edit(event, t(language, "ops.ticket.inbox"), buttons=buttons)

    @bot.on(events.CallbackQuery(pattern=rb"ops_tk_view_(?:user|admin)_(\w+)"))
    async def ticket_view(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        ticket_id = event.pattern_match.group(1).decode()
        ticket = ops_store.get_ticket(ticket_id)
        if not ticket:
            await event.answer(t(_language(user_id), "ops.ticket.not_found"), alert=True)
            return
        is_admin = DataManager.is_admin(user_id)
        if not is_admin and int(ticket.get("user_id", -1)) != user_id:
            await event.answer(t(_language(user_id), "ops.ticket.not_yours"), alert=True)
            return
        await event.answer()
        language = _language(user_id)
        lines = [f"#{ticket['id']} · {t(language, 'ops.ticket.status.' + ('open' if ticket.get('status') == 'open' else 'closed'))}"]
        for msg in ticket.get("messages", []):
            role = t(language, "ops.ticket.role.user") if msg.get("role") == "user" else t(language, "ops.ticket.role.admin")
            lines.append(f"{role}: {msg.get('text', '')}")
        buttons = []
        if is_admin and ticket.get("status") == "open":
            buttons.append([
                Button.inline(t(language, "ops.ticket.reply"), f"ops_tk_reply_{ticket['id']}".encode()),
                Button.inline(t(language, "ops.ticket.close"), f"ops_tk_close_{ticket['id']}".encode()),
            ])
        if not is_admin and ticket.get("status") == "open":
            buttons.append([Button.inline(t(language, "ops.ticket.reply"), f"ops_tk_reply_{ticket['id']}".encode())])
        if not is_admin and ticket.get("status") == "closed":
            buttons.append([Button.inline(t(language, "ops.ticket.reopen"), f"ops_tk_reopen_{ticket['id']}".encode())])
        buttons.append([
            back_button(b"ops_ticket_menu", language=language),
        ])
        set_state(user_id, **{_TICKET_VIEW_KEY: ticket_id})
        await safe_edit(event, "\n\n".join(lines), buttons=buttons)

    @bot.on(events.CallbackQuery(pattern=rb"ops_tk_reply_(\w+)"))
    async def ticket_reply(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        ticket_id = event.pattern_match.group(1).decode()
        ticket = ops_store.get_ticket(ticket_id)
        if not ticket or ticket.get("status") != "open":
            await event.answer(t(_language(user_id), "ops.ticket.not_open"), alert=True)
            return
        set_state(user_id, **{_TICKET_DRAFT_KEY: ticket_id})
        await event.answer()
        language = _language(user_id)
        await safe_edit(
            event,
            t(language, "ops.ticket.reply_prompt"),
            buttons=[[back_button(b"ops_ticket_menu", language=language)]],
        )

    @bot.on(events.NewMessage(func=lambda e: e.is_private))
    async def ticket_reply_capture(event):
        user_id = event.sender_id
        if not AccountManager.check_access(user_id):
            return
        state = get_state(user_id)
        ticket_id = state.get(_TICKET_DRAFT_KEY)
        if not ticket_id or not event.raw_text:
            return
        clear_state(user_id, _TICKET_DRAFT_KEY, _TICKET_VIEW_KEY)
        ticket = ops_store.get_ticket(ticket_id)
        if not ticket or ticket.get("status") != "open":
            await event.respond(t(_language(user_id), "ops.ticket.not_open"))
            return
        is_admin = DataManager.is_admin(user_id)
        if not is_admin and int(ticket.get("user_id", -1)) != user_id:
            await event.respond(t(_language(user_id), "ops.ticket.not_yours"))
            return
        now = time.time()
        ticket["messages"].append({
            "role": "admin" if is_admin else "user",
            "text": event.raw_text.strip(),
            "ts": now,
        })
        ticket["updated_at"] = now
        ops_store.upsert_ticket(ticket)
        reply_to = int(ticket["user_id"]) if is_admin else user_id
        language = _language(user_id)
        await event.respond(t(language, "ops.ticket.reply_sent"))
        if is_admin:
            # 通知用户
            try:
                await bot.send_message(
                    reply_to,
                    t(DataManager.get_user_language(reply_to), "ops.ticket.admin_reply",
                      ticket_id=ticket["id"], text=event.raw_text.strip()),
                )
            except Exception:
                logger.warning("工单管理员回复推送给用户失败: %s", reply_to)
        else:
            _notify_admins_about_ticket(
                bot, ticket,
                f"#{ticket['id']} 用户新消息: {event.raw_text.strip()[:100]}",
            )

    @bot.on(events.CallbackQuery(pattern=rb"ops_tk_close_(\w+)"))
    async def ticket_close(event):
        user_id = event.sender_id
        if not await require_admin(event, alert=True):
            return
        ticket_id = event.pattern_match.group(1).decode()
        ticket = ops_store.get_ticket(ticket_id)
        if not ticket:
            await event.answer(t(_language(user_id), "ops.ticket.not_found"), alert=True)
            return
        ticket["status"] = "closed"
        ticket["updated_at"] = time.time()
        ops_store.upsert_ticket(ticket)
        try:
            await bot.send_message(
                int(ticket["user_id"]),
                t(DataManager.get_user_language(int(ticket["user_id"])),
                  "ops.ticket.closed", ticket_id=ticket_id),
            )
        except Exception:
            logger.warning("工单关闭通知用户失败: %s", ticket["user_id"])
        await event.answer(t(_language(user_id), "ops.ticket.closed_ack"))

    @bot.on(events.CallbackQuery(pattern=rb"ops_tk_reopen_(\w+)"))
    async def ticket_reopen(event):
        user_id = event.sender_id
        if not await require_access(event, alert=True):
            return
        ticket_id = event.pattern_match.group(1).decode()
        ticket = ops_store.get_ticket(ticket_id)
        if not ticket or int(ticket.get("user_id", -1)) != user_id:
            await event.answer(t(_language(user_id), "ops.ticket.not_yours"), alert=True)
            return
        ticket["status"] = "open"
        ticket["updated_at"] = time.time()
        ops_store.upsert_ticket(ticket)
        await event.answer(t(_language(user_id), "ops.ticket.reopened"))
