import asyncio
import json
import os
from pyrogram import Client, filters
from pyrogram.types import Message

# -------------------------- 全局常量配置 --------------------------
DATA_FILE = "data.json"
# 官方短信发送机器人ID
SMS_BOT_ID = 777000

# -------------------------- 数据持久化工具函数 --------------------------
def load_storage():
    """加载本地存储数据，文件损坏/不存在自动返回空模板"""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return {
            "listeners": {},  # 存储监听手机号: {session名称, 是否启用}
            "target_users": [] # 接收验证码的用户ID列表
        }

def save_storage(data: dict):
    """保存数据到本地json文件"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# -------------------------- 全局初始化 --------------------------
# 主机器人客户端（指令交互机器人）
bot = Client(
    session_name="bot_main_session",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    ipv6=False
)

# 加载存储数据
storage = load_storage()
# 运行中的监听客户端池
running_listen_clients = {}

# -------------------------- 监听账号控制核心函数 --------------------------
async def start_phone_sms_listener(phone_number: str):
    """启动指定手机号的短信监听"""
    # 避免重复启动
    if phone_number in running_listen_clients:
        print(f"[INFO] {phone_number} 监听已运行，跳过")
        return

    session_name = storage["listeners"][phone_number]["session"]
    session_path = f"{session_name}.session"
    # 会话文件丢失直接终止
    if not os.path.exists(session_path):
        print(f"[ERROR] {phone_number} 会话文件 {session_path} 不存在，无法启动")
        return

    # 创建手机号监听客户端
    listen_client = Client(
        session_name,
        config.API_ID,
        config.API_HASH,
        ipv6=False
    )

    # 监听官方短信Bot发来的验证码
    @listen_client.on_message(filters.user(SMS_BOT_ID) & filters.private)
    async def capture_verification_code(_, msg: Message):
        print(f"[CAPTURE] {phone_number} 收到验证码：{msg.text}")
        # 批量转发给所有绑定用户
        for target_uid in storage["target_users"]:
            try:
                await bot.send_message(
                    chat_id=target_uid,
                    text=f"📩 手机号：{phone_number}\n验证码内容：{msg.text}"
                )
                print(f"[SEND] 验证码已推送至用户 {target_uid}")
            except Exception as err:
                print(f"[FAIL] 推送至 {target_uid} 失败：{str(err)}")

    # 启动监听客户端
    await listen_client.start()
    running_listen_clients[phone_number] = listen_client
    print(f"[SUCCESS] {phone_number} 短信监听已开启")

async def stop_phone_sms_listener(phone_number: str):
    """关闭指定手机号的监听"""
    if phone_number not in running_listen_clients:
        return
    try:
        await running_listen_clients[phone_number].stop()
    except Exception as err:
        print(f"[WARN] 关闭 {phone_number} 监听出现异常：{str(err)}")
    del running_listen_clients[phone_number]
    print(f"[STOP] {phone_number} 监听已关闭")

# -------------------------- 机器人交互指令函数 --------------------------
@bot.on_message(filters.command("start") & filters.private)
async def cmd_help(_, msg: Message):
    help_text = """🤖 Telegram 验证码转发机器人 操作手册
/add_listener    添加新的监听手机号（格式 +86133XXXXXXX）
/toggle +86号码  一键开启/关闭该号码监听
/list            查看全部已保存手机号及运行状态
/del +86号码     删除手机号并清理本地会话文件
/add_target ID   添加接收验证码的用户数字ID
/list_targets    查看所有接收验证码的用户ID
"""
    await msg.reply_text(help_text)

@bot.on_message(filters.command("add_listener") & filters.private)
async def cmd_add_phone(_, msg: Message):
    await msg.reply("📱 请发送完整国际格式手机号（示例：+8613362553093）")
    # 等待用户输入手机号，原生wait_for_message，无ask依赖
    try:
        phone_reply = await bot.wait_for_message(chat_id=msg.chat.id, timeout=120)
    except asyncio.TimeoutError:
        await msg.reply("⏱ 等待输入超时，请重新发送 /add_listener")
        return

    phone = phone_reply.text.strip()
    # 校验手机号是否已存在
    if phone in storage["listeners"]:
        await msg.reply("⚠️ 该手机号已录入系统，无需重复添加")
        return

    session_file_name = f"listen_{phone}"
    temp_login_client = Client(session_file_name, config.API_ID, config.API_HASH, ipv6=False)
    try:
        # 请求登录验证码
        code_response = await temp_login_client.send_code(phone)
        await msg.reply(f"✅ 登录验证码已下发至 {phone}，请回复收到的数字验证码")
        # 等待用户输入短信验证码
        try:
            code_reply = await bot.wait_for_message(chat_id=msg.chat.id, timeout=120)
        except asyncio.TimeoutError:
            await msg.reply("⏱ 验证码输入超时，本次添加流程终止")
            # 清理未完成的会话文件
            if os.path.exists(f"{session_file_name}.session"):
                os.remove(f"{session_file_name}.session")
            return

        verify_code = code_reply.text.strip()
        # 完成账号登录，保存会话
        await temp_login_client.sign_in(
            phone_number=phone,
            phone_code_hash=code_response.phone_code_hash,
            code=verify_code
        )
        await temp_login_client.stop()

        # 写入本地存储
        storage["listeners"][phone] = {
            "session": session_file_name,
            "enabled": True
        }
        save_storage(storage)
        # 自动启动监听
        await start_phone_sms_listener(phone)
        await msg.reply(f"🎉 {phone} 添加完成，短信监听已自动开启！发送 /list 查看列表")

    except Exception as err:
        await msg.reply(f"❌ 手机号登录失败：{str(err)}")
        # 登录失败清理残留会话
        if os.path.exists(f"{session_file_name}.session"):
            os.remove(f"{session_file_name}.session")

@bot.on_message(filters.command("toggle") & filters.private)
async def cmd_toggle(_, msg: Message):
    param = msg.text.split()
    if len(param) != 2:
        await msg.reply("❌ 格式错误，正确示例：/toggle +8613362553093")
        return
    target_phone = param[1]
    if target_phone not in storage["listeners"]:
        await msg.reply("❌ 系统内未找到该手机号，请先执行 /add_listener 添加")
        return

    # 切换启用状态
    old_state = storage["listeners"][target_phone]["enabled"]
    new_state = not old_state
    storage["listeners"][target_phone]["enabled"] = new_state
    save_storage(storage)

    if new_state:
        await start_phone_sms_listener(target_phone)
        await msg.reply(f"✅ {target_phone} 监听已开启")
    else:
        await stop_phone_sms_listener(target_phone)
        await msg.reply(f"⏹ {target_phone} 监听已关闭")

@bot.on_message(filters.command("list") & filters.private)
async def cmd_list_phone(_, msg: Message):
    if len(storage["listeners"]) == 0:
        await msg.reply("📭 暂无任何监听手机号，请使用 /add_listener 添加")
        return
    output_text = "📋 已保存手机号列表：\n"
    for phone, info in storage["listeners"].items():
        status_tag = "🟢 运行中" if info["enabled"] else "🔴 已关闭"
        output_text += f"- {phone} | {status_tag}\n"
    await msg.reply_text(output_text)

@bot.on_message(filters.command("del") & filters.private)
async def cmd_delete_phone(_, msg: Message):
    param = msg.text.split()
    if len(param) != 2:
        await msg.reply("❌ 格式错误，正确示例：/del +8613362553093")
        return
    target_phone = param[1]
    if target_phone not in storage["listeners"]:
        await msg.reply("❌ 未查询到该手机号记录")
        return

    # 停止监听并删除会话文件
    await stop_phone_sms_listener(target_phone)
    session_path = f"{storage['listeners'][target_phone]['session']}.session"
    if os.path.exists(session_path):
        os.remove(session_path)
    # 删除存储记录
    del storage["listeners"][target_phone]
    save_storage(storage)
    await msg.reply(f"🗑 {target_phone} 已彻底删除，本地会话文件已清理")

@bot.on_message(filters.command("add_target") & filters.private)
async def cmd_add_target(_, msg: Message):
    param = msg.text.split()
    if len(param) != 2 or not param[1].isdigit():
        await msg.reply("❌ 用法：/add_target 数字ID\n获取ID：TG搜索 @userinfobot 发送任意消息")
        return
    target_uid = int(param[1])
    if target_uid in storage["target_users"]:
        await msg.reply("⚠️ 该接收ID已存在，无需重复添加")
        return
    storage["target_users"].append(target_uid)
    save_storage(storage)
    await msg.reply(f"✅ 成功绑定接收用户ID：{target_uid}")

@bot.on_message(filters.command("list_targets") & filters.private)
async def cmd_list_target(_, msg: Message):
    if len(storage["target_users"]) == 0:
        await msg.reply("📭 暂无接收验证码的用户，请执行 /add_target 绑定你的ID")
        return
    text = "📋 验证码接收用户ID列表：\n" + "\n".join(map(str, storage["target_users"]))
    await msg.reply(text)

# -------------------------- 程序主入口 --------------------------
async def main():
    await bot.start()
    print("🤖 主机器人启动完成，等待指令...")
    # 程序启动自动恢复所有启用的监听
    for phone, info in storage["listeners"].items():
        if info["enabled"]:
            try:
                await start_phone_sms_listener(phone)
            except Exception as err:
                print(f"[WARN] 开机启动 {phone} 监听失败：{str(err)}")
    # 兼容全版本Pyrogram常驻等待，无.idle()属性报错
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
