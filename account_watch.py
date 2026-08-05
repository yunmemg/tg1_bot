import re
import logging
from telethon import events
from telethon.tl.functions.account import GetAuthorizationsRequest, ResetAuthorizationRequest
from login_lock import consume_code
from storage import get_phone_whitelist

logger = logging.getLogger("AccountWatch")
CODE_REGEX = re.compile(r"\b(\d{5,8})\b")

async def bind_captcha_listener(client, phone: str, admin_id: int, bot_client):
    @client.on(events.NewMessage(from_users=777000))
    async def captcha_handler(event):
        text = event.raw_text
        match = CODE_REGEX.search(text)
        if not match:
            return
        code = match.group(1)
        logger.info(f"[{phone}] 捕获登录验证码：{code}")

        # 获取账号所有已登录设备
        try:
            auth_result = await client(GetAuthorizationsRequest())
        except Exception as e:
            logger.error(f"[{phone}] 获取设备列表失败：{str(e)}")
            lock_result = await consume_code(phone, code)
            tip = f"⚠️ {phone} 获取设备异常，强制拦截，结果：{'成功作废' if lock_result else '拦截失败'}"
            await bot_client.send_message(admin_id, tip)
            return

        dev_full_map = {}
        all_device_full_names = []
        for auth_info in auth_result.authorizations:
            full_dev_name = f"{auth_info.device_model} ({auth_info.system_version})"
            dev_full_map[full_dev_name] = auth_info
            all_device_full_names.append(full_dev_name)

        white_list = get_phone_whitelist(admin_id, phone)
        untrusted_devices = [d for d in all_device_full_names if d not in white_list]

        if untrusted_devices:
            risk_device = untrusted_devices[0]
            logger.warning(f"[{phone}] 检测历史非白名单设备登录：{risk_device}")
        else:
            risk_device = "全新未登记陌生设备（无历史会话）"
            logger.warning(f"[{phone}] 全新设备登录，判定高风险强制拦截")

        # 执行登录锁作废验证码
        lock_success = await consume_code(phone, code)
        res_text = "✅ 验证码已失效拦截" if lock_success else "❌ 拦截失败（大概率TG限流）"

        notify_msg = (
            "🚨 异常登录拦截提醒\n"
            f"手机号：{phone}\n"
            f"验证码：{code}\n"
            f"风险设备：{risk_device}\n"
            f"处理结果：{res_text}"
        )
        await bot_client.send_message(admin_id, notify_msg)

        # 下线所有非白名单已登录设备
        for dev_name in untrusted_devices:
            auth_obj = dev_full_map.get(dev_name)
            if not auth_obj:
                continue
            try:
                await client(ResetAuthorizationRequest(hash=auth_obj.hash))
                logger.info(f"[{phone}] 已强制下线设备：{dev_name}")
            except Exception as e:
                logger.error(f"[{phone}] 下线设备 {dev_name} 失败：{str(e)}")