import os
# 强制东八区时区，消除容器时差导致验证码直接过期
os.environ["TZ"] = "Asia/Shanghai"

import asyncio
import logging
from logging.handlers import TimedRotatingFileHandler
import telethon
from telethon import TelegramClient
import config
from storage import init_storage
from bot_cmd import register_all_commands

# 日志过滤：屏蔽Telethon无用刷屏警告
class LogFilterUseless(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        useless_keywords = [
            "Server resent the older message",
            "Connection reset by peer",
            "0 bytes read on a total of"
        ]
        for kw in useless_keywords:
            if kw in msg:
                return False
        return True

def init_logger():
    os.makedirs(config.LOG_FOLDER, exist_ok=True)
    log_file_path = os.path.join(config.LOG_FOLDER, "run.log")
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    formatter = logging.Formatter(log_format)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.DEBUG)

    # 控制台输出
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, config.CONSOLE_LOG_LEVEL))
    console_handler.setFormatter(formatter)
    console_handler.addFilter(LogFilterUseless())
    root_logger.addHandler(console_handler)

    # 文件按日分割
    file_handler = TimedRotatingFileHandler(
        log_file_path,
        when="midnight",
        backupCount=config.LOG_SAVE_DAYS,
        encoding="utf-8"
    )
    file_handler.setLevel(getattr(logging, config.FILE_LOG_LEVEL))
    file_handler.setFormatter(formatter)
    file_handler.addFilter(LogFilterUseless())
    root_logger.addHandler(file_handler)

# 跨平台单进程锁，防止重复启动损坏session
class ProcessLock:
    def __init__(self, lock_path):
        self.path = lock_path
        self.file = None

    def acquire(self) -> bool:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        f = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            f.close()
            return False
        self.file = f
        return True

    def release(self):
        if not self.file:
            return
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        finally:
            self.file.close()
            self.file = None

bot_client = None

async def clean_resource():
    global bot_client
    logger = logging.getLogger("Clean")
    from bot_cmd import running_accounts
    logger.info("程序退出，开始清理资源")
    if bot_client:
        await bot_client.disconnect()
    running_accounts.clear()
    logger.info("资源清理完成")

async def main():
    global bot_client
    lock = ProcessLock(config.LOCK_FILE)
    if not lock.acquire():
        print("错误：程序已在运行，禁止重复启动")
        return
    try:
        init_logger()
        logger = logging.getLogger("Main")
        init_storage()
        os.makedirs(config.SESSIONS_DIR, exist_ok=True)
        logger.info(f"程序启动，Telethon版本：{telethon.__version__}")

        # 初始化机器人客户端
        bot_sess = os.path.join(config.SESSIONS_DIR, "bot.session")
        bot_client = TelegramClient(bot_sess, config.API_ID, config.API_HASH, auto_reconnect=True)
        register_all_commands(bot_client)
        await bot_client.start(bot_token=config.BOT_TOKEN)
        logger.info("🤖 机器人启动完成，等待指令")

        await bot_client.run_until_disconnected()
    except KeyboardInterrupt:
        logging.info("用户手动终止程序")
    except Exception as err:
        logging.exception("程序发生致命异常")
    finally:
        await clean_resource()
        lock.release()

if __name__ == "__main__":
    asyncio.run(main())