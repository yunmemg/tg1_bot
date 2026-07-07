import asyncio
import json
import os
from pyrogram import Client, filters
from pyrogram.types import Message

# 内置密钥，无需config.py
API_ID = 19684564
API_HASH = "6219dccd88035a229ec3aa84d8162a38"
BOT_TOKEN = "8754918048:AAEKWN7fBUZalgJpI3yJC31tc7wo6KFsp_Q"

DATA_FILE = "data.json"
SMS_BOT_ID = 777000

# 数据读写
def load_storage():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"listeners": {}, "target_users": []}

def save_storage(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# 主机器人
bot = Client(
    session_name="bot_main_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    ipv6_disabled=True
)

storage = load_storage()
running_listen_clients = {}

# 启动手机号监听
async def start_phone_sms_listener(phone_number: str):
    if phone_number in running_listen_clients:
        print(f"[INFO] {phone_number} 监听已运行，跳过")
        return
    session_name = storage["listeners"][phone_number]["session"]
    session_path = f"{session_name}.session"
    if not os.path.exists(session_path):
        print(f"[ERROR] {phone_number} 会话文件不存在，无法启动")
        return

    listen_client = Client(
        session_name,
        API_ID,
        API_HASH,
        ipv6_disabled=True
    )

    @listen_client.on_message(filters.user(SMS_BOT_ID) & filters.private)
    async def capture_verification_code(_, msg: Message):
        print(f"[CAPTURE] {phone_number} 收到验证码：{msg.text}")
        for target_uid in storage["target_users"]:
            try:
                await bot.send_message(target_uid, f"📩 手机号：{phone_number}\n验证码：{msg.text}")
                print(f"[SEND] 推送至 {target_uid} 成功")
            except Exception as err:
                print(f"[FAIL] 推送 {target_uid} 失败：{str(err)}")

    await listen_client.start()
    running_listen_clients[phone_number] = listen_client
    print(f"[SUCCESS] {phone_number} 监听已开启")

async def stop_phone_sms_listener(phone_number: str):
    if phone_number not in running_listen_clients:
        return
    try:
        await running_listen_clients[phone_number].stop()
    except Exception as err:
        print(f"[WARN] 关闭 {phone_number} 异常：{str(err)}")
    del running_listen_clients[phone_number]
    print(f"[STOP] {phone_number} 监听已关闭")

# /start 帮助指令
@bot.on_message(filters.command("start") & filters.private)
async def cmd_help(_, msg: Message):
    help_text = """🤖 验证码转发机器人
/add_listener    添加监听手机号（格式 +86133XXXXXXX）
/toggle +86号码  开关该号码监听
/list            查看全部手机号状态
/del +86号码     删除手机号并清理会话
/add_target ID   添加接收验证码用户ID
/list_targets    查看接收ID列表"""
    await msg.reply_text(help_text)

# 添加手机号
@bot.on_message(filters.command("add_listener") & filters.private)
async def cmd_add_phone(_, msg: Message):
    await msg.reply("📱 发送完整手机号，示例：+8613362553093")
    try:
        phone_reply = await bot.wait_for_message(chat_id=msg.chat.id, timeout=120)
    except asyncio.TimeoutError:
        await msg.reply("⏱ 输入超时，请重新执行 /add_listener")
        return
    phone = phone_reply.text.strip()
    if phone in storage["listeners"]:
        await msg.reply("⚠️ 该手机号已存在")
        return

    session_file_name = f"listen_{phone}"
    temp_login_client = Client(session_file_name, API_ID, API_HASH, ipv6_disabled=True)
    try:
        code_response = await temp_login_client.send_code(phone)
        await msg.reply(f"✅ 验证码已下发至 {phone}，请回复数字验证码")
        try:
            code_reply = await bot.wait_for_message(chat_id=msg.chat.id, timeout=120)
        except asyncio.TimeoutError:
            await msg.reply("⏱ 验证码输入超时，流程终止")
            if os.path.exists(f"{session_file_name}.session"):
                os.remove(f"{session_file_name}.session")
            return
        verify_code = code_reply.text.strip()
        await temp_login_client.sign_in(phone_number=phone, phone_code_hash=code_response.phone_code_hash, code=verify_code)
        await temp_login_client.stop()
        storage["listeners"][phone] = {"session": session_file_name, "enabled": True}
        save_storage(storage)
        await start_phone_sms_listener(phone)
        await msg.reply(f"🎉 {phone} 添加完成，监听已开启，发送 /list 查看")
    except Exception as err:
        await msg.reply(f"❌ 登录失败：{str(err)}")
        if os.path.exists(f"{session_file_name}.session"):
            os.remove(f"{session_file_name}.session")

# 开关监听
@bot.on_message(filters.command("toggle") & filters.private)
async def cmd_toggle(_, msg: Message):
    param = msg.text.split()
    if len(param) != 2:
        await msg.reply("❌ 格式示例：/toggle +8613362553093")
        return
    target_phone = param[1]
    if target_phone not in storage["listeners"]:
        await msg.reply("❌ 未找到该号码，请先 /add_listener")
        return
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

# 列出所有号码
@bot.on_message(filters.command("list") & filters.private)
async def cmd_list_phone(_, msg: Message):
    if not storage["listeners"]:
        await msg.reply("📭 暂无监听手机号，执行 /add_listener 添加")
        return
    output_text = "📋 手机号列表：\n"
    for phone, info in storage["listeners"].items():
        status_tag = "🟢 运行中" if info["enabled"] else "🔴 已关闭"
        output_text += f"- {phone} | {status_tag}\n"
    await msg.reply_text(output_text)

# 删除号码
@bot.on_message(filters.command("del") & filters.private)
async def cmd_delete_phone(_, msg: Message):
    param = msg.text.split()
    if len(param) != 2:
        await msg.reply("❌ 格式示例：/del +8613362553093")
        return
    target_phone = param[1]
    if target_phone not in storage["listeners"]:
        await msg.reply("❌ 未查询到此号码")
        return
    await stop_phone_sms_listener(target_phone)
    session_path = f"{storage['listeners'][target_phone]['session']}.session"
    if os.path.exists(session_path):
        os.remove(session_path)
    del storage["listeners"][target_phone]
    save_storage(storage)
    await msg.reply(f"🗑 {target_phone} 已彻底删除")

# 添加接收ID
@bot.on_message(filters.command("add_target") & filters.private)
async def cmd_add_target(_, msg: Message):
    param = msg.text.split()
    if len(param) != 2 or not param[1].isdigit():
        await msg.reply("❌ 用法：/add_target 数字ID\n搜 @userinfobot 获取ID")
        return
    target_uid = int(param[1])
    if target_uid in storage["target_users"]:
        await msg.reply("⚠️ 该接收ID已存在")
        return
    storage["target_users"].append(target_uid)
    save_storage(storage)
    await msg.reply(f"✅ 绑定接收ID：{target_uid}")

# 查看接收ID列表
@bot.on_message(filters.command("list_targets") & filters.private)
async def cmd_list_target(_, msg: Message):
    if not storage["target_users"]:
         await msg.reply("📭 暂无接收验证码用户ID")
         return
     text = "📋 接收ID列表：\n" + "\n".join(map(str, storage["target_users"]))
     await msg.reply(text)
 # 程序入口
 async def main():
     await bot.start()
     print("🤖 主机器人启动完成，等待指令...")
     for phone, info in storage["listeners"].items():
         if info["enabled"]:
             try:
                 await start_phone_sms_listener(phone)
             except Exception as err:
                 print(f"[WARN] 开机启动 {phone} 失败：{str(err)}")
     await asyncio.Event().wait()
 if __name__ == "__main__":
     asyncio.run(main())
