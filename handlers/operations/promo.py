# Copyright (c) 2026 秦屿泊 (@qinyubo)
# SPDX-License-Identifier: MIT

"""R6a 促销管理：管理员配置限时折扣，购买流程读取。"""

from __future__ import annotations

import logging
import time
import uuid
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

from telethon import TelegramClient, events
from telethon.tl.custom import Button

from handlers.handler_utils import back_button, require_admin, safe_edit
from handlers.operations import ops_store
from localization import t
from storage.data_manager import DataManager

logger = logging.getLogger(__name__)

PROMO_EMOJI = "🏷️"


def _language(user_id: int) -> str:
    return DataManager.get_user_language(user_id)


def apply_promotion_to_quote(quote: Dict) -> Dict:
    """若套餐存在有效促销，返回应用折扣后的报价副本；否则原样返回。"""
    plan_id = quote.get("plan_id", "")
    promo = ops_store.active_promotion_for(plan_id)
    if not promo:
        return quote
    try:
        discount = Decimal(str(promo.get("discount_percent", "0")))
        if discount <= 0 or discount >= 100:
            return quote
        base = Decimal(quote["price"])
        promoted = base * (Decimal("100") - discount) / Decimal("100")
        promoted = max(Decimal("0.5"), promoted)
        result = dict(quote)
        result["price"] = DataManager._decimal_text(promoted)
        result["promo_id"] = promo.get("id", "")
        result["promo_discount_percent"] = DataManager._decimal_text(discount)
        return result
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return quote


async def setup_promo_handlers(bot: TelegramClient) -> None:
    @bot.on(events.CallbackQuery(pattern=b"ops_promo"))
    async def promo_menu(event):
        if not await require_admin(event, alert=True):
            return
        await event.answer()
        language = _language(event.sender_id)
        promotions = ops_store.get_promotions()
        lines = [t(language, "ops.promo.menu")]
        if not promotions:
            lines.append(t(language, "ops.promo.empty"))
        for promo in promotions:
            plan = promo.get("plan_id", "")
            start = time.strftime("%m-%d %H:%M", time.localtime(float(promo.get("starts_at", 0))))
            end = time.strftime("%m-%d %H:%M", time.localtime(float(promo.get("ends_at", 0))))
            lines.append(
                f"`{promo.get('id', '')}` · {plan} · "
                f"-{promo.get('discount_percent', '0')}% · {start} ~ {end}"
            )
        buttons = [
            [Button.inline(t(language, "ops.promo.add"), b"ops_promo_add")],
            [back_button(b"back_to_main", language=language)],
        ]
        await safe_edit(event, "\n".join(lines), buttons=buttons, parse_mode="md")

    @bot.on(events.CallbackQuery(pattern=b"ops_promo_add"))
    async def promo_add(event):
        if not await require_admin(event, alert=True):
            return
        await event.answer()
        language = _language(event.sender_id)
        catalog = DataManager.get_subscription_catalog()
        buttons = [
            [Button.inline(plan["name"], f"ops_promo_plan_{pid}".encode())]
            for pid, plan in catalog.items()
        ]
        buttons.append([back_button(b"ops_promo", language=language)])
        await safe_edit(
            event,
            t(language, "ops.promo.choose_plan"),
            buttons=buttons,
        )

    @bot.on(events.CallbackQuery(pattern=rb"ops_promo_plan_(\w+)"))
    async def promo_plan(event):
        if not await require_admin(event, alert=True):
            return
        plan_id = event.pattern_match.group(1).decode()
        state_key = "ops_promo_plan"
        from handlers.handler_utils import set_state
        set_state(event.sender_id, **{state_key: plan_id})
        await event.answer()
        language = _language(event.sender_id)
        await safe_edit(
            event,
            t(language, "ops.promo.enter_discount"),
            buttons=[[back_button(b"ops_promo", language=language)]],
        )

    @bot.on(events.NewMessage(func=lambda e: e.is_private))
    async def promo_discount_capture(event):
        user_id = event.sender_id
        if not DataManager.is_admin(user_id):
            return
        from handlers.handler_utils import clear_state, get_state
        state = get_state(user_id)
        plan_id = state.get("ops_promo_plan")
        if not plan_id or not event.raw_text:
            return
        language = _language(user_id)
        try:
            discount = Decimal(event.raw_text.strip().rstrip("%"))
        except InvalidOperation:
            await event.respond(t(language, "ops.promo.invalid_discount"))
            return
        if discount <= 0 or discount >= 100:
            await event.respond(t(language, "ops.promo.invalid_discount"))
            return
        clear_state(user_id, "ops_promo_plan")
        now = time.time()
        promotions = ops_store.get_promotions()
        promotions.append({
            "id": f"PROMO-{uuid.uuid4().hex[:8].upper()}",
            "plan_id": plan_id,
            "discount_percent": DataManager._decimal_text(discount),
            "starts_at": now,
            "ends_at": now + 7 * 86400,
            "created_at": now,
        })
        if not ops_store.set_promotions(promotions):
            await event.respond(t(language, "ops.promo.save_failed"))
            return
        await event.respond(
            t(language, "ops.promo.added",
              plan=plan_id, discount=discount),
            buttons=[[Button.inline(t(language, "ops.promo.menu"), b"ops_promo")]],
        )
