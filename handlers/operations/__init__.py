# Copyright (c) 2026 秦屿泊 (@qinyubo)
# SPDX-License-Identifier: MIT

"""运营扩展模块：广播、工单、签到邀请、解限自动重登录、健康看板、促销、卡密、批量操作、自动续费。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telethon import TelegramClient

if TYPE_CHECKING:
    from payments.payment_system import PaymentSystem

logger = logging.getLogger(__name__)


async def setup_operations_handlers(
    bot: TelegramClient, payment_system: "PaymentSystem"
) -> None:
    """注册全部运营扩展事件处理器。"""
    from handlers.operations import broadcast, tickets, checkin_invite
    from handlers.operations import health_board, promo, redeem, batch_ops, auto_renew
    from handlers.operations import auto_relogin

    await broadcast.setup_broadcast_handlers(bot)
    await tickets.setup_ticket_handlers(bot)
    await checkin_invite.setup_checkin_invite_handlers(bot)
    await auto_relogin.setup_auto_relogin(bot)
    await health_board.setup_health_board_handlers(bot)
    await promo.setup_promo_handlers(bot)
    await redeem.setup_redeem_handlers(bot)
    await batch_ops.setup_batch_ops_handlers(bot)
    await auto_renew.setup_auto_renew_handlers(bot, payment_system)
    auto_renew.start_auto_renew_monitor(bot, payment_system)
    logger.info("✅ 运营扩展处理器已注册")
