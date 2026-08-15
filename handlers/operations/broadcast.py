# Copyright (c) 2026 秦屿泊 (@qinyubo)
# SPDX-License-Identifier: MIT

"""R1 公告/广播系统：定向筛选 + 人数预览 + 后台分批群发。"""

from __future__ import annotations

import asyncio
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
    require_admin,
    safe_edit,
    set_state,
)
from handlers.operations import ops_store
from localization import t
from storage.data_manager import DataManager

logger = logging.getLogger(__name__)

BROADCAST_MENU_EMOJI = "📢"

# 广播状态键
_BROADCAST_FILTER_KEY = "ops_broadcast_filter"
_BROADCAST_TEXT_KEY = "ops_broadcast_text"

_broadcast_tasks: Dict[str, asyncio.Task] = {}


def _language(user_id: int) -> str:
    return DataManager.get_user_language(user_id)


def _filter_options(language: str) -> List[List]:
    return [
        [
            Button.inline(t(language, "ops.broadcast.all"), b"ops_bc_f_all"),
            Button.inline(t(language, "ops.broadcast.subscribed"), b"ops_bc_f_sub"),
        ],
        [
            Button.inline(t(language, "ops.broadcast.unsubscribed"), b"ops_bc_f_unsub"),
            Button.inline(t(language, "ops.broadcast.expiring"), b"ops_bc_f_expire"),
        ],
        [
            Button.inline(t(language, "ops.broadcast.by_plan"), b"ops_bc_f_plan"),
            back_button(b"back_to_main"),
        ],
    ]


def _collect_target_user_ids(filter_key: str) -> List[int]:
    """按筛选条件收集目标用户 ID。"""
    user_ids: List[int] = []
    now = time.time()
    for user_id in DataManager.get_all_user_ids():
        if not str(user_id).isdigit():
            continue
        uid = int(user_id)
        if DataManager.is_admin(uid):
            continue
        subscription = DataManager.get_subscription(uid)
        active = subscription is not None and bool(subscription.get("active"))
        if filter_key == "all":
            user_ids.append(uid)
        elif filter_key == "sub":
            if active:
                user_ids.append(uid)
        elif filter_key == "unsub":
            if not active:
                user_ids.append(uid)
        elif filter_key == "expire":
            if active:
                try:
                    expires_at = (
                        __import__("datetime").datetime.fromisoformat(
                            subscription["expires_at"]
                        )
                    ).timestamp()
                    if 0 <= (expires_at - now) <= 7 * 86400:
                        user_ids.append(uid)
                except (KeyError, TypeError, ValueError):
                    continue
    return user_ids


def _apply_broadcast_text(state: Dict, user_id: int, text: str) -> bool:
    state[_BROADCAST_TEXT_KEY] = text
    return True


async def _run_broadcast(
    bot: TelegramClient,
    broadcast_id: str,
    target_ids: List[int],
    text: str,
    with_button: bool,
) -> Dict:
    """后台分批群发。"""
    ok, fail = 0, 0
    failed_ids: List[int] = []
    for uid in target_ids:
        try:
            buttons = None
            if with_button:
                buttons = [
                    [Button.inline(
                        t(DataManager.get_user_language(uid), "ops.broadcast.open"),
                        b"back_to_main",
                    )]
                ]
            await bot.send_message(uid, text, buttons=buttons)
            ok += 1
        except account_runtime.NotifyBotFatalError:
            raise
        except Exception as error:
            fail += 1
            failed_ids.append(uid)
            logger.warning(
                "广播发送失败: 用户ID=%s, 广播ID=%s, 错误=%s",
                uid, broadcast_id, type(error).__name__,
            )
        await asyncio.sleep(0.08)
    return {"ok": ok, "fail": fail, "failed_ids": failed_ids}


async def setup_broadcast_handlers(bot: TelegramClient) -> None:
    @bot.on(events.CallbackQuery(pattern=b"ops_broadcast"))
    async def broadcast_menu(event):
        if not await require_admin(event, alert=True):
            return
        await event.answer()
        language = _language(event.sender_id)
        text = t(language, "ops.broadcast.menu")
        buttons = [
            [Button.inline(t(language, "ops.broadcast.start"), b"ops_bc_start")],
            [Button.inline(t(language, "ops.broadcast.history"), b"ops_bc_history")],
            [back_button(b"back_to_main", language=language)],
        ]
        await safe_edit(event, text, buttons=buttons)

    @bot.on(events.CallbackQuery(pattern=b"ops_bc_start"))
    async def broadcast_start(event):
        if not await require_admin(event, alert=True):
            return
        await event.answer()
        language = _language(event.sender_id)
        await safe_edit(
            event,
            t(language, "ops.broadcast.choose_filter"),
            buttons=_filter_options(language),
        )

    @bot.on(events.CallbackQuery(pattern=rb"ops_bc_f_\w+"))
    async def broadcast_filter(event):
        if not await require_admin(event, alert=True):
            return
        filter_key = event.data.decode().replace("ops_bc_f_", "")
        if filter_key == "plan":
            await event.answer()
            language = _language(event.sender_id)
            catalog = DataManager.get_subscription_catalog()
            buttons = [
                [Button.inline(plan["name"], f"ops_bc_plan_{pid}".encode())]
                for pid, plan in catalog.items()
            ]
            buttons.append([back_button(b"ops_broadcast", language=language)])
            await safe_edit(
                event, t(language, "ops.broadcast.choose_plan"), buttons=buttons
            )
            return
        set_state(event.sender_id, **{_BROADCAST_FILTER_KEY: filter_key})
        count = len(_collect_target_user_ids(filter_key))
        await event.answer()
        language = _language(event.sender_id)
        await safe_edit(
            event,
            t(language, "ops.broadcast.enter_text", count=count),
            buttons=[[back_button(b"ops_broadcast", language=language)]],
        )

    @bot.on(events.CallbackQuery(pattern=rb"ops_bc_plan_\w+"))
    async def broadcast_filter_plan(event):
        if not await require_admin(event, alert=True):
            return
        plan_id = event.data.decode().replace("ops_bc_plan_", "")
        set_state(event.sender_id, **{_BROADCAST_FILTER_KEY: f"plan:{plan_id}"})
        count = len(_collect_target_user_ids(f"plan:{plan_id}"))
        await event.answer()
        language = _language(event.sender_id)
        await safe_edit(
            event,
            t(language, "ops.broadcast.enter_text", count=count),
            buttons=[[back_button(b"ops_broadcast", language=language)]],
        )

    @bot.on(events.NewMessage(func=lambda e: e.is_private))
    async def broadcast_text_capture(event):
        user_id = event.sender_id
        if not DataManager.is_admin(user_id):
            return
        state = get_state(user_id)
        if state.get(_BROADCAST_TEXT_KEY):
            return
        filter_key = state.get(_BROADCAST_FILTER_KEY)
        if not filter_key or not event.raw_text:
            return
        clear_state(user_id, _BROADCAST_FILTER_KEY)
        if not _apply_broadcast_text(state, user_id, event.raw_text):
            return
        target_ids = _collect_target_user_ids(filter_key)
        text = event.raw_text
        await event.respond(
            t(_language(user_id), "ops.broadcast.preview",
              count=len(target_ids), text=text),
            buttons=[
                [
                    Button.inline(t(_language(user_id), "ops.broadcast.confirm_send"), b"ops_bc_send"),
                    Button.inline(t(_language(user_id), "common.cancel"), b"ops_bc_cancel"),
                ]
            ],
        )

    @bot.on(events.CallbackQuery(pattern=b"ops_bc_send"))
    async def broadcast_confirm(event):
        if not await require_admin(event, alert=True):
            return
        user_id = event.sender_id
        state = get_state(user_id)
        text = state.get(_BROADCAST_TEXT_KEY)
        if not text:
            await event.answer(t(_language(user_id), "ops.broadcast.no_text"), alert=True)
            return
        clear_state(user_id, _BROADCAST_TEXT_KEY)
        filter_key = state.get(_BROADCAST_FILTER_KEY) or "all"
        target_ids = _collect_target_user_ids(filter_key)
        language = _language(user_id)
        broadcast_id = f"BC-{int(time.time())}"
        ops_store.add_broadcast({
            "id": broadcast_id,
            "filter": filter_key,
            "target_count": len(target_ids),
            "text": text,
            "created_at": time.time(),
            "status": "running",
        })
        await event.answer()
        await safe_edit(
            event,
            t(language, "ops.broadcast.sending", count=len(target_ids)),
            buttons=[[back_button(b"ops_broadcast", language=language)]],
        )
        task = asyncio.create_task(
            _run_broadcast(bot, broadcast_id, target_ids, text, with_button=False)
        )
        _broadcast_tasks[broadcast_id] = task

        def _done(t: asyncio.Task):
            _broadcast_tasks.pop(broadcast_id, None)
            try:
                result = t.result()
            except account_runtime.NotifyBotFatalError:
                raise
            except Exception as error:
                result = {"ok": 0, "fail": len(target_ids), "failed_ids": list(target_ids)}
                logger.exception("广播执行异常: %s", broadcast_id)
            record = ops_store.get_broadcast(broadcast_id) or {}
            record["status"] = "done"
            record["result"] = result
            ops_store.save_broadcast(record)
            asyncio.create_task(
                bot.send_message(
                    user_id,
                    t(language, "ops.broadcast.done",
                      ok=result["ok"], fail=result["fail"]),
                )
            )

        task.add_done_callback(_done)

    @bot.on(events.CallbackQuery(pattern=b"ops_bc_cancel"))
    async def broadcast_cancel(event):
        if not await require_admin(event, alert=True):
            return
        clear_state(event.sender_id, _BROADCAST_TEXT_KEY, _BROADCAST_FILTER_KEY)
        await event.answer(t(_language(event.sender_id), "ops.broadcast.cancelled"))
        language = _language(event.sender_id)
        await safe_edit(
            event,
            t(language, "ops.broadcast.menu"),
            buttons=[
                [Button.inline(t(language, "ops.broadcast.start"), b"ops_bc_start")],
                [Button.inline(t(language, "ops.broadcast.history"), b"ops_bc_history")],
                [back_button(b"ops_broadcast", language=language)],
            ],
        )

    @bot.on(events.CallbackQuery(pattern=b"ops_bc_history"))
    async def broadcast_history(event):
        if not await require_admin(event, alert=True):
            return
        await event.answer()
        language = _language(event.sender_id)
        items = ops_store.list_broadcasts(limit=10)
        if not items:
            await safe_edit(
                event,
                t(language, "ops.broadcast.empty"),
                buttons=[[back_button(b"ops_broadcast", language=language)]],
            )
            return
        lines = []
        for item in items:
            result = item.get("result") or {}
            lines.append(
                f"{item.get('id')} · {len(str(item.get('text', '')))}字 · "
                f"目标{item.get('target_count', 0)} · "
                f"成功{result.get('ok', 0)}/失败{result.get('fail', 0)}"
            )
        await safe_edit(
            event,
            t(language, "ops.broadcast.history_text") + "\n\n" + "\n".join(lines),
            buttons=[[back_button(b"ops_broadcast", language=language)]],
        )
