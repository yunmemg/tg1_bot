import asyncio
import json
import os
from pyrogram import Client, filters
from pyrogram.types import Message
import config

DATA_FILE = "data.json"

def load_data():
    try:
        with open(DATA_FILE, 'r', encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"listeners": {}, "targets": []}

def save_data(data):
    with open(DATA_FILE, 'w', encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# 机器人客户端初始化
bot_client = Client(
    "bot_session",
    config.API_ID,
    config.API_HASH,
    bot_token=config.BOT_TOKEN,
    ipv6=False
)
data = load_data()
active_listeners = {}

async def start_listener(phone):
    if phone in active_listeners:
        print(f"[{phone}] 监听已存在，无需重复启动")
        return
    session_name = data['listeners'][phone]['session']
    session_path = f"{session_name}.session"
    if not os.path.exists(session_path):
        print(f"[{phone}] 会话文件不存在，跳过启动")
        return
        
    listen_client = Client(
        session_name,
        config.API_ID,
        config.API_HASH,
        ipv6=False
    )

    @listen_client.on_message(filters.user(777000) & filters.private)
    async def sms_handler(_, message):
        print(f"[{phone}] 收到验证码：{message.text}")
        for target_id in data['targets']:
            try:
                await bot_client.send_message(target_id, f"📨 验证码 ({phone}):\n{message.text}")
                print(f"[{phone}] 成功转发至 {target_id}")
            except Exception as e:
                print(f"[{phone}] 转发目标 {target_id} 失败: {str(e)}")

    await listen_client.start()
    active_listeners[phone] = listen_client
    print(f"✅ {phone} 监听已开启，等待短信...")

async def stop_listener(phone):
    if phone in active_listeners:
        try:
            await active_listeners[phone].stop()
        except Exception as e:
            print(f"[{phone}] 关闭监听异常: {str(e)}")
        del active_listeners[phone]
        print(f"⏸ {phone} 监听已关闭")

@bot_client.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    help_text = (
        "🤖 验证码转发机器人已启动！\n\n"
        "命令列表：\n"
        "/add_listener - 添加监听号码\n"
        "/toggle +86xxx - 开关监听\n"
        "/list - 查看所有号码\n"
        "/del +86xxx - 删除号码\n"
        "/add_target 用户ID - 添加转发目标\n"
        "/list_targets - 查看转发目标"
    )
    await message.reply_text(help_text)

@bot_client.on_message(filters.command("add_listener") & filters.private)
async def add_listener(client, message):
    await message.reply("📱 请发送手机号（国际格式，如 +8613812345678）：")
    try:
        phone_msg = await client.wait_for_message(chat_id=message.chat.id, timeout=120)
    except asyncio.TimeoutError:
        await message.reply("⏱ 等待输入超时，请重新执行 /add_listener")
        return
        
    phone = phone_msg.text.strip()
    if phone in data['listeners']:
        return await message.reply("⚠️ 该号码已存在，请勿重复添加。")
    
    session_name = f"listener_{phone}"
    new_client = Client(
        session_name,
        config.API_ID,
        config.API_HASH,
        ipv6=False
    )
    
    try:
        # 发送验证码
        sent_code = await new_client.send_code(phone)
        await message.reply(f"✅ 验证码已发送至 {phone}，请回复短信内数字验证码：")
        # 等待用户输入验证码
        try:
            code_msg = await client.wait_for_message(chat_id=message.chat.id, timeout=120)
        except asyncio.TimeoutError:
            await message.reply("⏱ 验证码输入超时，请重新发起添加")
            if os.path.exists(f"{session_name}.session"):
                os.remove(f"{session_name}.session")
            return
            
        code = code_msg.text.strip()
        # 登录账号
        await new_client.sign_in(phone, sent_code.phone_code_hash, code)
        await new_client.stop()
        
        # 写入数据并保存
        data['listeners'][phone] = {"session": session_name, "enabled": True}
        save_data(data)
        await start_listener(phone)
        await message.reply(f"🎉 {phone} 添加成功，监听已开启！执行 /list 可查看")
    except Exception as e:
        await message.reply(f"❌ 登录失败：{str(e)}")
        if os.path.exists(f"{session_name}.session"):
            os.remove(f"{session_name}.session")

@bot_client.on_message(filters.command("toggle") & filters.private)
async def toggle_listener(client, message):
    parts = message.text.split()
    if len(parts) != 2:
        return await message.reply("用法：/toggle +8613812345678")
    phone = parts[1]
    if phone not in data['listeners']:
        return await message.reply("❌ 未找到该号码，请先执行 /add_listener 添加")
    
    current_state = data['listeners'][phone]['enabled']
    new_state = not current_state
    data['listeners'][phone]['enabled'] = new_state
    save_data(data)
    
    if new_state:
        await start_listener(phone)
        await message.reply(f"✅ {phone} 已开启转发")
    else:
        await stop_listener(phone)
        await message.reply(f"⏸ {phone} 已关闭转发")

@bot_client.on_message(filters.command("list") & filters.private)
async def list_listeners(client, message):
    if not data['listeners']:
        return await message.reply("📭 尚未添加任何监听号码，请先执行 /add_listener")
    text = "📋 监听号码列表：\n"
    for phone, info in data['listeners'].items():
        status = "🟢 开启" if info['enabled'] else "🔴 关闭"
        text += f"- {phone} ({status})\n"
    await message.reply(text)

@bot_client.on_message(filters.command("del") & filters.private)
async def del_listener(client, message):
    parts = message.text.split()
    if len(parts) != 2:
        return await message.reply("用法：/del +8613812345678")
    phone = parts[1]
    if phone in data['listeners']:
        await stop_listener(phone)
        session_path = f"{data['listeners'][phone]['session']}.session"
        if os.path.exists(session_path):
            os.remove(session_path)
        del data['listeners'][phone]
        save_data(data)
        await message.reply(f"🗑 {phone} 已彻底删除")
    else:
        await message.reply("❌ 未找到该号码")

@bot_client.on_message(filters.command("add_target") & filters.private)
async def add_target(client, message):
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return await message.reply("用法：/add_target <用户ID>\n获取ID请搜索 @userinfobot")
    target = int(parts[1])
    if target not in data['targets']:
        data['targets'].append(target)
        save_data(data)
        await message.reply(f"✅ 已添加转发目标 {target}")
    else:
        await message.reply("⚠️ 该目标已存在")

@bot_client.on_message(filters.command("list_targets") & filters.private)
async def list_targets(client, message):
    if data['targets']:
        text = "📋 转发目标列表：\n" + "\n".join(map(str, data['targets']))
        await message.reply(text)
    else:
        await message.reply("📭 暂无转发目标，请执行 /add_target 绑定你的ID")

async def main():
    await bot_client.start()
    print("🤖 机器人主程序已启动！")
    # 自动恢复所有启用的监听
    for phone, info in data['listeners'].items():
        if info['enabled']:
            try:
                await start_listener(phone)
            except Exception as e:
                print(f"启动 {phone} 监听失败: {str(e)}")
    # Pyrogram官方稳定常驻，不会无故退出容器
    await bot_client.idle()

if __name__ == "__main__":
    asyncio.run(main())
