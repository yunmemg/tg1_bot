import asyncio
import json
import os
from pyrogram import Client, filters
from pyrogram.types import Message
import config

# 数据存储文件
DATA_PATH = "data.json"

# 读取数据
def load_json():
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"listeners": {}, "targets": []}

# 保存数据
def save_json(data):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# 主机器人实例
bot = Client(
    session_name="bot_main",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    ipv6=False
)

# 全局变量
db = load_json()
running_listen = {}

# ====================== 监听账号启停函数 ======================
async def start_phone_listen(phone_num: str):
    if phone_num in running_listen:
        print(f"[{phone_num}] 监听已在运行，跳过")
        return
    session_name = db["listeners"][phone_num]["session"]
    session_file = f"{session_name}.session"
    if not os.path.exists(session_file):
        print(f"[{phone_num}] 会话文件丢失，无法启动")
        return

    # 创建监听客户端
    listen_cli = Client(
        session_name,
        config.API_ID,
        config.API_HASH,
        ipv6=False
    )

    # 捕获官方短信Bot 777000发来的验证码
    @listen_cli.on_message(filters.user(777000) & filters.private)
    async def catch_code(_, msg: Message):
        print(f"[{phone_num}] 收到验证码：{msg.text}")
        # 批量转发所有绑定用户
        for user_id in db["targets"]:
            try:
                await bot.send_message(user_id, f"📩 手机号 {phone_num}\n验证码：{msg.text}")
                print(f"[{phone_num}] 转发至 {user_id} 成功")
            except Exception as e:
                print(f"[{phone_num}] 转发 {user_id} 失败：{str(e)}")

    await listen_cli.start()
    running_listen[phone_num] = listen_cli
    print(f"✅ [{phone_num}] 监听启动完成")

async def stop_phone_listen(phone_num: str):
    if phone_num not in running_listen:
        return
    try:
        await running_listen[phone_num].stop()
    except Exception as e:
        print(f"[{phone_num}] 关闭监听异常：{str(e)}")
    del running_listen[phone_num]
    print(f"⏹ [{phone_num}] 监听已关闭")

# ====================== 机器人指令 ======================
@bot.on_message(filters.command("start") & filters.private)
async def cmd_start(_, msg: Message):
    help_text = """🤖 验证码转发机器人 指令大全
/add_listener  添加新的监听手机号
/toggle +8613800000000  开启/关闭该号码监听
/list  查看全部监听号码状态
/del +8613800000000  删除号码并清除会话
/add_target 123456789  添加接收验证码的用户ID
/list_targets  查看所有接收ID"""
    await msg.reply_text(help_text)

@bot.on_message(filters.command("add_listener") & filters.private)
async def cmd_add(_, msg: Message):
    await msg.reply("📱 请发送手机号（完整国际格式，例：+8613362553093）")
    # 等待用户输入手机号
    try:
        phone_msg = await bot.wait_for_message(chat_id=msg.chat.id, timeout=120)
    except asyncio.TimeoutError:
        await msg.reply("⏱ 等待超时，请重新执行 /add_listener")
        return
    phone = phone_msg.text.strip()
    if phone in db["listeners"]:
        return await msg.reply("⚠️ 该手机号已存在，无需重复添加")
    
    session_name = f"listen_{phone}"
    temp_cli = Client(session_name, config.API_ID, config.API_HASH, ipv6=False)
    try:
        # 请求登录验证码
        code_data = await temp_cli.send_code(phone)
        await msg.reply(f"✅ 验证码已下发至 {phone}，请回复收到的数字验证码")
        # 等待用户输入验证码
        try:
            code_input = await bot.wait_for_message(chat_id=msg.chat.id, timeout=120)
        except asyncio.TimeoutError:
            await msg.reply("⏱ 验证码输入超时，本次添加终止")
            if os.path.exists(f"{session_name}.session"):
                os.remove(f"{session_name}.session")
            return
        code = code_input.text.strip()
        # 完成登录保存会话
        await temp_cli.sign_in(phone, code_data.phone_code_hash, code)
        await temp_cli.stop()
        # 写入数据库
        db["listeners"][phone] = {"session": session_name, "enabled": True}
        save_json(db)
        # 自动启动监听
        await start_phone_listen(phone)
        await msg.reply(f"🎉 {phone} 添加成功，监听已自动开启！发送 /list 查看")
    except Exception as err:
        await msg.reply(f"❌ 登录失败：{str(err)}")
        if os.path.exists(f"{session_name}.session"):
            os.remove(f"{session_name}.session")

@bot.on_message(filters.command("toggle") & filters.private)
async def cmd_toggle(_, msg: Message):
    args = msg.text.split()
    if len(args) != 2:
        return await msg.reply("❌ 用法示例：/toggle +8613362553093")
    phone = args[1]
    if phone not in db["listeners"]:
        return await msg.reply("❌ 未查询到此号码，请先执行 /add_listener 添加")
    # 切换启用状态
    current_state = db["listeners"][phone]["enabled"]
    new_state = not current_state
    db["listeners"][phone]["enabled"] = new_state
    save_json(db)
    if new_state:
        await start_phone_listen(phone)
        await msg.reply(f"✅ {phone} 监听已开启")
    else:
        await stop_phone_listen(phone)
        await msg.reply(f"⏹ {phone} 监听已关闭")

@bot.on_message(filters.command("list") & filters.private)
async def cmd_list(_, msg: Message):
    if not db["listeners"]:
        return await msg.reply("📭 暂无任何监听号码，请执行 /add_listener 添加")
    text = "📋 监听号码列表：\n"
    for phone, info in db["listeners"].items():
        status = "🟢 运行中" if info["enabled"] else "🔴 已关闭"
        text += f"- {phone} | {status}\n"
    await msg.reply(text)

@bot.on_message(filters.command("del") & filters.private)
async def cmd_del(_, msg: Message):
    args = msg.text.split()
    if len(args) != 2:
        return await msg.reply("❌ 用法示例：/del +8613362553093")
    phone = args[1]
    if phone not in db["listeners"]:
        return await msg.reply("❌ 未找到该号码")
    # 停止监听+删除会话文件
    await stop_phone_listen(phone)
    session_file = f"{db['listeners'][phone]['session']}.session"
    if os.path.exists(session_file):
        os.remove(session_file)
    # 删除数据库记录
    del db["listeners"][phone]
    save_json(db)
    await msg.reply(f"🗑 {phone} 已彻底删除，会话文件已清理")

@bot.on_message(filters.command("add_target") & filters.private)
async def cmd_add_target(_, msg: Message):
    args = msg.text.split()
    if len(args) != 2 or not args[1].isdigit():
        return await msg.reply("❌ 用法：/add_target 你的数字ID\n获取ID搜索 @userinfobot")
    target_id = int(args[1])
    if target_id in db["targets"]:
        return await msg.reply("⚠️ 该接收ID已存在")
    db["targets"].append(target_id)
    save_json(db)
    await msg.reply(f"✅ 成功添加接收ID：{target_id}")

@bot.on_message(filters.command("list_targets") & filters.private)
async def cmd_list_targets(_, msg: Message):
    if not db["targets"]:
        return await msg.reply("📭 暂无接收验证码的用户ID，请执行 /add_target")
    text = "📋 验证码接收目标ID列表：\n" + "\n".join(map(str, db["targets"]))
    await msg.reply(text)

# ====================== 程序入口 ======================
async def main():
    await bot.start()
    print("🤖 主机器人启动成功！")
    # 程序启动时自动恢复所有开启的监听
    for phone, info in db["listeners"].items():
        if info["enabled"]:
            try:
                await start_phone_listen(phone)
            except Exception as e:
                print(f"启动 {phone} 监听失败：{str(e)}")
    # 兼容所有Pyrogram版本，稳定常驻不闪退
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
