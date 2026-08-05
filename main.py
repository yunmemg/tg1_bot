# -*- coding: utf-8 -*-
import asyncio
import json
import os
import re
import logging
from datetime import datetime
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl.functions.account import GetAuthorizationsRequest, InvalidateSignInCodesRequest
import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

os.makedirs(config.SESSIONS_DIR, exist_ok=True)

# ========== 数据管理 ==========
def load_accounts():
    if os.path.exists(config.ACCOUNTS_FILE):
        with open(config.ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_accounts(accounts):
    with open(config.ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)

# ========== 本地化通知 ==========
def get_notify_text(lang, code, phone, device_name, status="blocked"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if lang == "zh":
        if status == "blocked":
            return (
                "🚨 **异常登录拦截提醒**\n\n"
                "⚠️ 发现异常登录行为\n"
                "🛡️ 系统已拦截验证码，登录请求强制失效\n\n"
                f"🔢 **验证码：** `{code}`\n"
                f"📞 **目标账户：** `{phone}`\n"
                f"💻 **非白名单设备：** {device_name}\n"
                f"⏰ **拦截时间：** {now}\n\n"
                "请检查你的登录设备，确认是否本人操作。"
            )
        else:
            return (
                "❌ **拦截失败**\n\n"
                "系统未能成功作废验证码，请手动检查登录活动。\n"
                f"📞 账户：`{phone}`\n"
                f"⏰ 时间：{now}"
            )
    else:
        if status == "blocked":
            return (
                "🚨 **Suspicious Login Blocked**\n\n"
                "⚠️ Unauthorized login attempt detected\n"
                "🛡️ Verification code has been invalidated\n\n"
                f"🔢 **Code:** `{code}`\n"
                f"📞 **Account:** `{phone}`\n"
                f"💻 **Untrusted Device:** {device_name}\n"
                f"⏰ **Time:** {now}\n\n"
                "Please check your active sessions."
            )
        else:
            return (
                "❌ **Block Failed**\n\n"
                "Could not invalidate the code. Please manually check your account.\n"
                f"📞 Account: `{phone}`\n"
                f"⏰ Time: {now}"
            )

# ========== Bot 客户端 ==========
bot = TelegramClient(
    os.path.join(config.SESSIONS_DIR, "bot"),
    config.API_ID,
    config.API_HASH,
    connection_retries=5,
    retry_delay=3,
).start(bot_token=config.BOT_TOKEN)

clients = {}

async def start_phone_client(phone, user_id):
    session_path = os.path.join(config.SESSIONS_DIR, f"{phone}.session")
    client = TelegramClient(
        session_path,
        config.API_ID,
        config.API_HASH,
        connection_retries=5,
        retry_delay=3,
        auto_reconnect=True,
    )
    try:
        await client.start(phone=phone)
    except Exception as e:
        logger.error(f"启动客户端失败 {phone}: {e}")
        await bot.send_message(user_id, f"❌ 启动监听失败 {phone}: {e}")
        return None

    clients[phone] = client

    @client.on(events.NewMessage(from_users=777000))
    async def handler(event):
        accounts = load_accounts()
        uid = str(user_id)
        if uid not in accounts or phone not in accounts[uid]:
            return
        if not accounts[uid][phone].get("enabled", True):
            return

        match = re.search(r'\b(\d{5,8})\b', event.raw_text)
        if not match:
            return
        code = match.group(1)
        logger.info(f"[{phone}] 捕获验证码: {code}")

        # 获取设备列表（新版调用）
        try:
            auths = await client(GetAuthorizationsRequest())
        except Exception as e:
            logger.error(f"[{phone}] 获取设备列表失败: {e}")
            await bot.send_message(user_id, f"⚠️ 无法获取设备列表，请手动检查。\n{phone}")
            return

        devices = []
        for auth in auths.authorizations:
            device_id = f"{auth.device_model} ({auth.system_version})"
            devices.append({
                "id": device_id,
                "device_model": auth.device_model,
                "system_version": auth.system_version,
                "hash": auth.hash
            })

        whitelist = accounts[uid][phone].get("whitelist", [])
        untrusted = [d for d in devices if d["id"] not in whitelist and d["device_model"] not in whitelist]
        if not untrusted:
            logger.info(f"[{phone}] 所有设备均在白名单中，放行")
            return

        device_name = untrusted[0]["id"]
        # 作废验证码（新版调用）
        try:
            await client(InvalidateSignInCodesRequest(codes=[code]))
            logger.info(f"[{phone}] 验证码 {code} 已作废")
            status = "blocked"
        except Exception as e:
            logger.error(f"[{phone}] 作废失败: {e}")
            status = "failed"

        text = get_notify_text(config.DEFAULT_LANG, code, phone, device_name, status)
        try:
            await bot.send_message(user_id, text, parse_mode='markdown')
        except Exception as e:
            logger.error(f"发送通知给 {user_id} 失败: {e}")

    try:
        await client.run_until_disconnected()
    except Exception as e:
        logger.error(f"[{phone}] 客户端异常断开: {e}")
    finally:
        clients.pop(phone, None)

# ========== Bot 命令 ==========
@bot.on(events.NewMessage(pattern='/start'))
async def start_cmd(event):
    await event.reply(
        "🤖 **反登录机器人 (白名单版)**\n\n"
        "添加你的手机号，我会监控登录验证码，\n"
        "只有**非白名单设备**发起的登录才会被拦截。\n\n"
        "**命令：**\n"
        "/add +8613800138000 - 添加托管号码\n"
        "/list - 查看你的托管号码\n"
        "/remove +8613800138000 - 移除托管号码\n"
        "/status - 查看各号码状态\n"
        "/whitelist +8613800138000 - 查看该号码的白名单\n"
        "/add_device +86... 设备名 - 添加设备到白名单\n"
        "/remove_device +86... 设备名 - 从白名单移除\n"
        "/enable +8613800138000 - 开启该号码防护\n"
        "/disable +8613800138000 - 关闭该号码防护\n"
        "/help - 显示此帮助"
    )

@bot.on(events.NewMessage(pattern='/add'))
async def add_cmd(event):
    user_id = event.sender_id
    args = event.raw_text.split()
    if len(args) < 2:
        await event.reply("❌ 请提供手机号，例如：`/add +8613800138000`")
        return
    phone = args[1]
    if not phone.startswith('+'):
        phone = '+' + phone

    accounts = load_accounts()
    uid = str(user_id)
    if uid in accounts and phone in accounts[uid]:
        await event.reply(f"⚠️ 手机号 {phone} 已在你的托管列表中。")
        return

    session_path = os.path.join(config.SESSIONS_DIR, f"{phone}.session")
    client = TelegramClient(session_path, config.API_ID, config.API_HASH)

    try:
        await client.connect()
        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            await event.reply(f"📱 验证码已发送至 {phone}，请输入验证码（回复此消息）：")

            @bot.on(events.NewMessage(from_users=user_id))
            async def code_reply(ev):
                code = ev.raw_text.strip()
                if not code.isdigit():
                    await ev.reply("❌ 验证码必须是数字，重新输入或 /cancel")
                    return
                try:
                    await client.sign_in(phone, code)
                except SessionPasswordNeededError:
                    await ev.reply("🔐 该账户启用了两步验证，请输入二级密码：")
                    @bot.on(events.NewMessage(from_users=user_id))
                    async def password_reply(pev):
                        pwd = pev.raw_text.strip()
                        try:
                            await client.sign_in(password=pwd)
                        except Exception as e:
                            await pev.reply(f"❌ 登录失败: {e}")
                            return
                        await finish_add(phone, user_id, client)
                        bot.remove_event_handler(code_reply)
                        bot.remove_event_handler(password_reply)
                    return
                except Exception as e:
                    await ev.reply(f"❌ 登录失败: {e}")
                    return
                await finish_add(phone, user_id, client)
                bot.remove_event_handler(code_reply)
        else:
            await finish_add(phone, user_id, client)
    except Exception as e:
        await event.reply(f"❌ 添加失败: {e}")
    finally:
        if client and client.is_connected():
            await client.disconnect()

async def finish_add(phone, user_id, client):
    accounts = load_accounts()
    uid = str(user_id)
    if uid not in accounts:
        accounts[uid] = {}
    if phone not in accounts[uid]:
        accounts[uid][phone] = {"whitelist": [], "enabled": True}
        save_accounts(accounts)
    if client and client.is_connected():
        await client.disconnect()
    asyncio.create_task(start_phone_client(phone, user_id))
    await bot.send_message(user_id, f"✅ 手机号 {phone} 已添加，反登录监控已启动")

@bot.on(events.NewMessage(pattern='/list'))
async def list_cmd(event):
    user_id = str(event.sender_id)
    accounts = load_accounts()
    data = accounts.get(user_id, {})
    if not data:
        await event.reply("📭 你还没有添加任何托管号码。")
        return
    lines = []
    for phone, info in data.items():
        status = "✅" if info.get("enabled", True) else "⏸"
        lines.append(f"{status} {phone} (白名单 {len(info.get('whitelist', []))}个设备)")
    await event.reply("📋 **你的托管号码：**\n\n" + "\n".join(lines))

@bot.on(events.NewMessage(pattern='/remove'))
async def remove_cmd(event):
    user_id = str(event.sender_id)
    args = event.raw_text.split()
    if len(args) < 2:
        await event.reply("❌ 请提供要移除的手机号，例如：`/remove +8613800138000`")
        return
    phone = args[1]
    accounts = load_accounts()
    if user_id not in accounts or phone not in accounts[user_id]:
        await event.reply(f"⚠️ 手机号 {phone} 不在你的托管列表中。")
        return
    del accounts[user_id][phone]
    if not accounts[user_id]:
        del accounts[user_id]
    save_accounts(accounts)
    if phone in clients:
        try:
            await clients[phone].disconnect()
        except:
            pass
        clients.pop(phone, None)
    await event.reply(f"✅ 已移除 {phone}，监控已停止。")

@bot.on(events.NewMessage(pattern='/status'))
async def status_cmd(event):
    user_id = str(event.sender_id)
    accounts = load_accounts()
    data = accounts.get(user_id, {})
    if not data:
        await event.reply("📭 没有托管号码。")
        return
    lines = []
    for phone in data:
        if phone in clients and clients[phone].is_connected():
            lines.append(f"✅ {phone} - 在线")
        else:
            lines.append(f"❌ {phone} - 离线")
    await event.reply("📊 **连接状态：**\n\n" + "\n".join(lines))

@bot.on(events.NewMessage(pattern='/whitelist'))
async def whitelist_cmd(event):
    user_id = str(event.sender_id)
    args = event.raw_text.split()
    if len(args) < 2:
        await event.reply("❌ 请指定手机号，例如：`/whitelist +8613800138000`")
        return
    phone = args[1]
    accounts = load_accounts()
    if user_id not in accounts or phone not in accounts[user_id]:
        await event.reply(f"⚠️ 手机号 {phone} 不在你的托管列表中。")
        return
    whitelist = accounts[user_id][phone].get("whitelist", [])
    if not whitelist:
        await event.reply(f"📭 {phone} 的白名单为空。")
    else:
        lines = [f"{i+1}. {dev}" for i, dev in enumerate(whitelist)]
        await event.reply(f"📋 **{phone} 的白名单设备：**\n\n" + "\n".join(lines))

@bot.on(events.NewMessage(pattern='/add_device'))
async def add_device_cmd(event):
    user_id = str(event.sender_id)
    args = event.raw_text.split(maxsplit=2)
    if len(args) < 3:
        await event.reply("❌ 格式：`/add_device +8613800138000 设备名称`")
        return
    phone = args[1]
    device = args[2].strip()
    accounts = load_accounts()
    if user_id not in accounts or phone not in accounts[user_id]:
        await event.reply(f"⚠️ 手机号 {phone} 不在你的托管列表中。")
        return
    whitelist = accounts[user_id][phone].setdefault("whitelist", [])
    if device in whitelist:
        await event.reply(f"⚠️ `{device}` 已在白名单中。")
        return
    whitelist.append(device)
    save_accounts(accounts)
    await event.reply(f"✅ 已添加 `{device}` 到 {phone} 的白名单。")

@bot.on(events.NewMessage(pattern='/remove_device'))
async def remove_device_cmd(event):
    user_id = str(event.sender_id)
    args = event.raw_text.split(maxsplit=2)
    if len(args) < 3:
        await event.reply("❌ 格式：`/remove_device +8613800138000 设备名称`")
        return
    phone = args[1]
    device = args[2].strip()
    accounts = load_accounts()
    if user_id not in accounts or phone not in accounts[user_id]:
        await event.reply(f"⚠️ 手机号 {phone} 不在你的托管列表中。")
        return
    whitelist = accounts[user_id][phone].get("whitelist", [])
    if device not in whitelist:
        await event.reply(f"⚠️ `{device}` 不在白名单中。")
        return
    whitelist.remove(device)
    save_accounts(accounts)
    await event.reply(f"✅ 已移除 `{device}` 从 {phone} 的白名单。")

@bot.on(events.NewMessage(pattern='/enable'))
async def enable_cmd(event):
    user_id = str(event.sender_id)
    args = event.raw_text.split()
    if len(args) < 2:
        await event.reply("❌ 请指定手机号，例如：`/enable +8613800138000`")
        return
    phone = args[1]
    accounts = load_accounts()
    if user_id not in accounts or phone not in accounts[user_id]:
        await event.reply(f"⚠️ 手机号 {phone} 不在你的托管列表中。")
        return
    accounts[user_id][phone]["enabled"] = True
    save_accounts(accounts)
    await event.reply(f"✅ {phone} 的防护已开启。")

@bot.on(events.NewMessage(pattern='/disable'))
async def disable_cmd(event):
    user_id = str(event.sender_id)
    args = event.raw_text.split()
    if len(args) < 2:
        await event.reply("❌ 请指定手机号，例如：`/disable +8613800138000`")
        return
    phone = args[1]
    accounts = load_accounts()
    if user_id not in accounts or phone not in accounts[user_id]:
        await event.reply(f"⚠️ 手机号 {phone} 不在你的托管列表中。")
        return
    accounts[user_id][phone]["enabled"] = False
    save_accounts(accounts)
    await event.reply(f"⏸ {phone} 的防护已暂停。")

@bot.on(events.NewMessage(pattern='/help'))
async def help_cmd(event):
    await start_cmd(event)

@bot.on(events.NewMessage(pattern='/cancel'))
async def cancel_cmd(event):
    await event.reply("⏹ 操作已取消。")

# ========== 启动 ==========
async def main():
    accounts = load_accounts()
    for uid, phones in accounts.items():
        for phone in phones:
            if phone not in clients:
                asyncio.create_task(start_phone_client(phone, int(uid)))
    await bot.run_until_disconnected()

if __name__ == "__main__":
    logger.info("🤖 反登录机器人 (白名单版, 适配新版Telethon) 启动中...")
    asyncio.run(main())