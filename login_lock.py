import os
import logging
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    SessionPasswordNeededError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError
)
import config

logger = logging.getLogger("LoginLock")

async def consume_code(phone: str, code: str) -> bool:
    temp_session_path = os.path.join(config.SESSIONS_DIR, f"{config.TEMP_LOCK_SESS_PREFIX}{phone}")
    temp_client = TelegramClient(temp_session_path, config.API_ID, config.API_HASH)
    try:
        await temp_client.connect()
        logger.info(f"[{phone}] 执行登录锁，验证码：{code}")
        await temp_client.sign_in(phone, code=code)
        await temp_client.log_out()
        logger.info(f"[{phone}] ✅ 验证码已成功作废")
        return True
    except SessionPasswordNeededError:
        logger.warning(f"[{phone}] 账号开启2FA，验证码已消耗失效")
        return True
    except PhoneCodeExpiredError:
        logger.warning(f"[{phone}] 验证码本身已过期")
        return False
    except PhoneCodeInvalidError:
        logger.warning(f"[{phone}] 验证码无效")
        return False
    except FloodWaitError as err:
        logger.error(f"[{phone}] 触发TG限流，需等待 {err.seconds} 秒")
        return False
    except Exception as err:
        logger.error(f"[{phone}] 登录锁异常：{str(err)}")
        return False
    finally:
        await temp_client.disconnect()
        # 清理临时会话文件
        for suffix in ("", ".session", ".session-journal"):
            full_path = temp_session_path + suffix
            if os.path.exists(full_path):
                os.remove(full_path)