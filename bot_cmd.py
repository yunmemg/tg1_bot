import asyncio
import logging
from telethon import events
import config
from storage import add_white_device, remove_white_device, get_phone_whitelist
from account_watch import bind_captcha_listener

logger = logging.getLogger("BotCommand")
running_accounts = dict()
background_task_set = set()

def register_all_commands(bot):
    @bot.on(events.NewMessage(pattern="/start|/help"))
    async def help_cmd(event):
        help_text = """🤖 TG反登录白名单锁机器人
指令清单：
/add +86手机号    添加托管监控账号
/list             查看已托管号码
/status           查看账号在线状态
/whitelist +86xxx 查看该号码白名单设备
/add_device +86xxx 设备全称  添加信任设备
/remove_device +86xxx 设备全称  删除白名单设备
"""
        await event.reply(help_text)

    @bot.on(events.NewMessage(pattern="/add"))
    async def add_account(event):
        sender_uid = event.sender_id
        args = event.raw_text.split()
        if len(args) < 2:
            await event.reply("格式错误，示例：/add +8613800000000")
            return
        target_phone = args[1]
        session_path = f"{config.SESSIONS_DIR}/{target_phone}.session"
        from telethon import TelegramClient
        acc_client = TelegramClient(session_path, config.API_ID, config.API_HASH)
        try:
            await acc_client.connect()
            if not await acc_client.is_user_authorized():
                await acc_client.send_code_request(target_phone)
                await event.reply(f"{target_phone} 验证码已下发，请直接回复数字验证码登录")

                @bot.on(events.NewMessage(from_users=sender_uid))
                async def code_input_handler(ev):
                    code_input = ev.raw_text.strip()
                    if not code_input.isdigit():
                        await ev.reply("验证码只能为纯数字")
                        return
                    try:
                        await acc_client.sign_in(target_phone, code=code_input)
                    except Exception as err:
                        await ev.reply(f"登录失败：{str(err)}")
                        return
                    await finish_start_account(target_phone, sender_uid, acc_client, bot)
                    bot.remove_event_handler(code_input_handler)
                return
            await finish_start_account(target_phone, sender_uid, acc_client, bot)
        except Exception as err:
            await event.reply(f"账号添加失败：{str(err)}")
        finally:
            if acc_client.is_connected():
                await acc_client.disconnect()

    async def finish_start_account(phone, admin_uid, acc_client, bot):
        if phone in running_accounts:
            await bot.send_message(admin_uid, f"{phone} 已处于监控运行中")
            return
        task = asyncio.create_task(start_single_account(phone, admin_uid, bot))
        background_task_set.add(task)
        task.add_done_callback(background_task_set.discard)
        running_accounts[phone] = True
        await bot.send_message(admin_uid, f"✅ {phone} 登录成功，验证码防护已启动")

    async def start_single_account(phone, admin_uid, bot):
        from telethon import TelegramClient
        sess_file = f"{config.SESSIONS_DIR}/{phone}.session"
        cli = TelegramClient(sess_file, config.API_ID, config.API_HASH, auto_reconnect=True)
        try:
            await cli.connect()
            await bind_captcha_listener(cli, phone, admin_uid, bot)
            await cli.run_until_disconnected()
        except Exception as err:
            logger.error(f"[{phone}] 监听进程断开：{str(err)}")
        finally:
            running_accounts.pop(phone, None)
            await cli.disconnect()

    @bot.on(events.NewMessage(pattern="/list"))
    async def list_account(event):
        if not running_accounts:
            await event.reply("暂无托管监控账号")
            return
        text = "当前托管号码：\n" + "\n".join(running_accounts.keys())
        await event.reply(text)

    @bot.on(events.NewMessage(pattern="/status"))
    async def status_cmd(event):
        if not running_accounts:
            await event.reply("无在线账号")
            return
        lines = [f"✅ {p} 在线监控中" for p in running_accounts]
        await event.reply("\n".join(lines))

    @bot.on(events.NewMessage(pattern="/whitelist"))
    async def show_white(event):
        uid = event.sender_id
        args = event.raw_text.split()
        if len(args) < 2:
            await event.reply("格式：/whitelist +8613800000000")
            return
        phone = args[1]
        dev_list = get_phone_whitelist(uid, phone)
        if not dev_list:
            await event.reply(f"{phone} 的设备白名单为空")
            return
        text = f"{phone} 信任设备列表：\n" + "\n".join(dev_list)
        await event.reply(text)

    @bot.on(events.NewMessage(pattern="/add_device"))
    async def add_dev_white(event):
        uid = event.sender_id
        args = event.raw_text.split(maxsplit=2)
        if len(args) < 3:
            await event.reply("格式：/add_device +86xxx 设备全称")
            return
        phone, dev_name = args[1], args[2]
        ok = add_white_device(uid, phone, dev_name)
        if ok:
            await event.reply(f"✅ {dev_name} 已加入 {phone} 白名单")
        else:
            await event.reply(f"⚠️ {dev_name} 已存在白名单")

    @bot.on(events.NewMessage(pattern="/remove_device"))
    async def remove_dev_white(event):
        uid = event.sender_id
        args = event.raw_text.split(maxsplit=2)
        if len(args) < 3:
            await event.reply("格式：/remove_device +86xxx 设备全称")
            return
        phone, dev_name = args[1], args[2]
        ok = remove_white_device(uid, phone, dev_name)
        if ok:
            await event.reply(f"✅ {dev_name} 已从白名单移除")
        else:
            await event.reply(f"⚠️ 不存在该设备")