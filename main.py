import asyncio
import os
import re
import time
import logging
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    AuthKeyDuplicatedError,
    FloodWaitError,
)
from telethon.tl.functions.account import ResetAuthorizationsRequest
from telethon.tl.functions.auth import SendCodeRequest
from telethon.tl.types import CodeSettings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "logs", "security.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telethon').setLevel(logging.WARNING)

# ===================== 配置区 =====================
API_ID = 19684564          # 替换为你的 API ID
API_HASH = "6219dccd88035a229ec3aa84d8162a38"  # 替换为你的 API HASH
BOT_TOKEN = "8754918048:AAEKWN7fBUZalgJpI3yJC31tc7wo6KFsp_Q"  # 替换为你的机器人令牌

# 管理员ID：只有这些ID可以操作机器人，留空则所有人都能操作（不建议）
ADMIN_IDS = []  # 例如 [123456789, 987654321]

# 防御开关
AUTO_INVALIDATE_CODE = True   # 检测到登录后自动重发验证码使旧码失效
AUTO_KICK_SESSIONS = True     # 检测到登录后自动终止所有其他设备
COOLDOWN_SECONDS = 60         # 同一账号冷却时间，避免重复触发
# ==================================================

accounts = {}
user_login_states = {}
last_trigger_time = {}
PHONE_RULE = re.compile(r'^\+\d{10,15}$')
CODE_REGEX = re.compile(r'\b\d{4,6}\b')

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
SESSION_DIR = os.path.join(os.path.dirname(__file__), "sessions")
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(SESSION_DIR, exist_ok=True)


def redact_code(text: str) -> str:
    """脱敏验证码数字，不显示具体码值。"""
    return CODE_REGEX.sub("[验证码已隐藏]", text)


def is_admin(user_id: int) -> bool:
    if not ADMIN_IDS:
        return True
    return user_id in ADMIN_IDS


async def invalidate_code(client: TelegramClient, phone: str) -> bool:
    """主动发送新验证码，使旧验证码失效。"""
    try:
        await client(SendCodeRequest(
            phone_number=phone,
            api_id=API_ID,
            api_hash=API_HASH,
            settings=CodeSettings(
                allow_flashcall=False,
                current_number=True,
                allow_app_hash=False,
                allow_missed_call=False,
            ),
        ))
        logger.warning(f"[{phone}] 已主动发送新验证码，旧码已失效")
        return True
    except FloodWaitError as e:
        logger.error(f"[{phone}] 触发频率限制，需等待 {e.seconds} 秒")
        return False
    except Exception as e:
        logger.error(f"[{phone}] 重发验证码失败: {str(e)}")
        return False


async def kick_all_sessions(client: TelegramClient, phone: str) -> bool:
    """一键终止所有其他设备会话。"""
    try:
        await client(ResetAuthorizationsRequest())
        logger.warning(f"[{phone}] 已终止所有其他设备会话")
        return True
    except Exception as e:
        logger.error(f"[{phone}] 终止会话失败: {str(e)}")
        return False


async def notify_admin(text: str):
    """给所有管理员发送通知。"""
    targets = ADMIN_IDS if ADMIN_IDS else []
    for admin_id in targets:
        try:
            await bot_client.send_message(admin_id, text)
        except Exception as e:
            logger.error(f"发送通知给 {admin_id} 失败: {str(e)}")


def bind_account_handlers(client: TelegramClient, phone: str):
    @client.on(events.NewMessage(outgoing=True))
    async def alive_test(event):
        if event.message.text and event.message.text.lower() == "self check":
            await event.edit(text="✅ self checked! 程序运行正常")
            logger.info(f"[{phone}] 存活检测")

    @client.on(events.NewMessage(outgoing=True, pattern=r"(?i)^antilogin$"))
    async def query_status(event):
        stat = "ON ✅" if accounts[phone]["anti_login"] else "OFF ❌"
        auto_inval = "已开启" if AUTO_INVALIDATE_CODE else "已关闭"
        auto_kick = "已开启" if AUTO_KICK_SESSIONS else "已关闭"
        await event.edit(text=(
            f"Anti-login 状态: {stat}\n\n"
            f"防御策略:\n"
            f"- 验证码自动作废: {auto_inval}\n"
            f"- 其他设备自动下线: {auto_kick}\n"
            f"- 冷却时间: {COOLDOWN_SECONDS}秒\n\n"
            f"发送 antilogin on 开启\n"
            f"发送 antilogin off 关闭"
        ))
        logger.info(f"[{phone}] 查询反登录状态: {stat}")

    @client.on(events.NewMessage(outgoing=True, pattern=r"(?i)^antilogin on$"))
    async def enable_push(event):
        accounts[phone]["anti_login"] = True
        await event.edit(text="✅ 反登录防护已开启\n\n收到验证码时将自动执行:\n1. 旧验证码作废\n2. 其他设备下线\n3. 机器人发送告警")
        logger.info(f"[{phone}] 反登录已开启")
        await notify_admin(f"✅ {phone} 反登录防护已手动开启")

    @client.on(events.NewMessage(outgoing=True, pattern=r"(?i)^antilogin off$"))
    async def disable_push(event):
        accounts[phone]["anti_login"] = False
        await event.edit(text="❌ 反登录防护已关闭")
        logger.info(f"[{phone}] 反登录已关闭")
        await notify_admin(f"⚠️ {phone} 反登录防护已手动关闭")

    @client.on(events.NewMessage(from_users=[777000]))
    async def capture_code(event):
        text = event.message.text or ""
        anti_on = accounts[phone]["anti_login"]
        logger.info(f"[{phone}] 收到777000消息, anti_login={anti_on}")

        if not anti_on:
            return

        # 冷却判断
        now_ts = time.time()
        if phone in last_trigger_time and now_ts - last_trigger_time[phone] < COOLDOWN_SECONDS:
            logger.info(f"[{phone}] 冷却期内，跳过防御触发")
            return
        last_trigger_time[phone] = now_ts

        # 判断是否是验证码消息
        is_code_msg = bool(CODE_REGEX.search(text)) and any(
            kw in text.lower() for kw in ["login code", "登录代码", "验证码", "telegram code", "code for", "登录", "code:"]
        )

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        code_invalidated = False
        sessions_kicked = False

        if is_code_msg:
            logger.critical(f"[{phone}] 检测到登录验证码消息，启动主动防御")

            if AUTO_INVALIDATE_CODE:
                code_invalidated = await invalidate_code(client, phone)
            if AUTO_KICK_SESSIONS:
                sessions_kicked = await kick_all_sessions(client, phone)

            actions = []
            actions.append("✅ 旧验证码已作废" if code_invalidated else "⚠️ 验证码作废失败")
            actions.append("✅ 其他设备已全部下线" if sessions_kicked else "⚠️ 设备下线失败")

            alert_text = (
                f"🚨 Telegram 反登录防护触发\n\n"
                f"账号：{phone}\n"
                f"时间：{now_str}\n"
                f"风险：极高危\n\n"
                f"已执行动作：\n" + "\n".join(f"- {a}" for a in actions) + "\n\n"
                f"消息内容（已脱敏）：\n{redact_code(text)}\n\n"
                f"请立即确认是否本人操作！"
            )
            await notify_admin(alert_text)

            try:
                await event.reply(
                    "🚨 反登录主动防御已执行\n"
                    "旧验证码已作废\n"
                    "所有其他设备已下线\n"
                    "请确认是否本人操作"
                )
            except Exception:
                pass
        else:
            # 非验证码的官方消息，也可选通知
            logger.info(f"[{phone}] 收到777000非验证码消息")


bot_client = TelegramClient(
    os.path.join(SESSION_DIR, "management_bot"),
    API_ID,
    API_HASH,
)


@bot_client.on(events.NewMessage(pattern=r"(?i)^/start$"))
async def help_menu(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ 你没有权限使用此机器人")
        return
    text = """🤖 Telegram 反登录机器人命令列表

【用户号私聊命令】
在已登录的账号自己的 Saved Messages 或任意会话发送：
self check        检测程序是否存活
antilogin         查看反登录开关状态
antilogin on      开启反登录防护
antilogin off     关闭反登录防护

【机器人私聊命令】
/addphone +8613800138000    添加并登录新的监控手机号
/listphone                  列出所有已登录账号
/delphone +8613800138000    删除手机号会话
/logout +861380000000       远程登出手机号所有设备

📌 防护逻辑：
收到777000登录验证码时自动：
1. 发送新验证码使旧码作废
2. 终止所有其他设备会话
3. 给本机器人发告警（验证码已脱敏）
"""
    await event.reply(text)


@bot_client.on(events.NewMessage(pattern=r"(?i)^/addphone (.+)"))
async def add_phone(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ 你没有权限使用此机器人")
        return
    phone = event.pattern_match.group(1).strip()
    if not PHONE_RULE.match(phone):
        await event.reply("❌ 手机号格式错误，示例：/addphone +8613800138000")
        return
    if phone in accounts:
        await event.reply("⚠️ 该手机号已登录")
        return
    session_name = os.path.join(SESSION_DIR, f"session_{phone.replace('+','')}")
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
        await event.reply(f"✅ 验证码已发送到 {phone}\n请直接回复收到的数字验证码完成登录")
        logger.info(f"[{phone}] 已发送登录验证码，等待输入")
    except PhoneNumberInvalidError:
        await event.reply("❌ 手机号无效")
    except AuthKeyDuplicatedError:
        await event.reply("❌ 该账号已在其他设备登录，请先下线其他会话")
    except FloodWaitError as e:
        await event.reply(f"❌ 请求过于频繁，请等待 {e.seconds} 秒后重试")
    except Exception as e:
        await event.reply(f"❌ 发送验证码失败：{str(e)}")


@bot_client.on(events.NewMessage)
async def login_process(event):
    if event.sender_id not in user_login_states:
        return
    if not is_admin(event.sender_id):
        return
    state = user_login_states[event.sender_id]
    input_text = event.raw_text.strip() if event.raw_text else ""

    # 忽略命令
    if input_text.startswith("/"):
        return

    if state["step"] == "input_sms_code":
        if not input_text.isdigit():
            await event.reply("请输入纯数字验证码")
            return
        try:
            await state["client"].sign_in(
                phone=state["phone"],
                phone_code_hash=state["code_hash"],
                code=input_text
            )
            accounts[state["phone"]] = {
                "client": state["client"],
                "anti_login": False
            }
            bind_account_handlers(state["client"], state["phone"])
            del user_login_states[event.sender_id]
            await event.reply(
                f"✅ {state['phone']} 登录完成！\n\n"
                f"默认反登录状态：OFF\n"
                f"请在该账号任意会话发送 antilogin on 开启防护"
            )
            logger.info(f"[{state['phone']}] 登录成功")
        except SessionPasswordNeededError:
            state["step"] = "input_2fa_password"
            await event.reply("🔐 该账号开启了两步验证，请回复两步验证密码")
        except PhoneCodeInvalidError:
            await event.reply("❌ 验证码错误，请重新使用 /addphone 重试")
            del user_login_states[event.sender_id]
        except Exception as e:
            await event.reply(f"❌ 登录失败：{str(e)}")
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
            await event.reply(
                f"✅ {state['phone']} 两步验证通过，登录完成！\n\n"
                f"默认反登录状态：OFF\n"
                f"请发送 antilogin on 开启防护"
            )
            logger.info(f"[{state['phone']}] 2FA验证通过，登录成功")
        except Exception as e:
            await event.reply(f"❌ 两步验证密码错误，请重新使用 /addphone 重试：{str(e)}")
            del user_login_states[event.sender_id]


@bot_client.on(events.NewMessage(pattern=r"(?i)^/listphone$"))
async def list_all(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ 你没有权限使用此机器人")
        return
    if not accounts:
        await event.reply("📭 暂无已登录的监控账号，请使用 /addphone 添加")
        return
    output = "📋 已登录账号列表：\n\n"
    for num, data in accounts.items():
        status = "🟢 防护开启" if data["anti_login"] else "🔴 防护关闭"
        output += f"- {num} | {status}\n"
    await event.reply(output)


@bot_client.on(events.NewMessage(pattern=r"(?i)^/delphone (.+)"))
async def delete_session(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ 你没有权限使用此机器人")
        return
    phone = event.pattern_match.group(1).strip()
    if phone not in accounts:
        await event.reply("❌ 未找到该手机号")
        return
    try:
        await accounts[phone]["client"].disconnect()
    except Exception:
        pass
    del accounts[phone]
    session_file = os.path.join(SESSION_DIR, f"session_{phone.replace('+','')}.session")
    if os.path.exists(session_file):
        os.remove(session_file)
    await event.reply(f"✅ {phone} 会话已删除")
    logger.info(f"[{phone}] 会话已删除")


@bot_client.on(events.NewMessage(pattern=r"(?i)^/logout (.+)"))
async def remote_logout(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ 你没有权限使用此机器人")
        return
    phone = event.pattern_match.group(1).strip()
    if phone not in accounts:
        await event.reply("❌ 未找到该手机号")
        return
    try:
        await accounts[phone]["client"].log_out()
        await accounts[phone]["client"].disconnect()
        del accounts[phone]
        session_file = os.path.join(SESSION_DIR, f"session_{phone.replace('+','')}.session")
        if os.path.exists(session_file):
            os.remove(session_file)
        await event.reply(f"✅ {phone} 已远程登出所有设备")
        logger.info(f"[{phone}] 已远程登出所有设备")
    except Exception as e:
        await event.reply(f"❌ 远程登出失败：{str(e)}")


async def main():
    print("=" * 50)
    print("Telegram 反登录机器人启动中...")
    print(f"自动作废验证码: {'开启' if AUTO_INVALIDATE_CODE else '关闭'}")
    print(f"自动下线设备: {'开启' if AUTO_KICK_SESSIONS else '关闭'}")
    print(f"管理员ID: {ADMIN_IDS if ADMIN_IDS else '未限制（所有人可操作）'}")
    print("=" * 50)

    await bot_client.start(bot_token=BOT_TOKEN)
    bot_me = await bot_client.get_me()
    print(f"管理机器人已上线: @{bot_me.username}")
    print("发送 /start 查看命令列表")

    await notify_admin(
        f"✅ Telegram 反登录机器人已启动\n\n"
        f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"自动作废验证码：{'开启' if AUTO_INVALIDATE_CODE else '关闭'}\n"
        f"自动下线设备：{'开启' if AUTO_KICK_SESSIONS else '关闭'}\n"
        f"当前已登录账号数：{len(accounts)}\n\n"
        f"发送 /start 查看命令"
    )

    await bot_client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序已停止")
