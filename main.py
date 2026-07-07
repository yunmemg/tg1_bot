import asyncio
import json
import os
from pyrogram import Client, filters
from pyrogram.types import Message

# 直接写密钥，不需要config.py文件
API_ID = 19684564
API_HASH = "6219dccd88035a229ec3aa84d8162a38"
BOT_TOKEN = "8754918048:AAEKWN7fBUZalgJpI3yJC31tc7wo6KFsp_Q"

# -------------------------- 全局常量配置 --------------------------
DATA_FILE = "data.json"
SMS_BOT_ID = 777000

# 初始化客户端时直接使用变量，不再调用config.xxx
bot = Client(
    session_name="bot_main_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    ipv6=False
)
