import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ALLOWED_USER_IDS: list[int] = [
        int(x.strip())
        for x in os.getenv("ALLOWED_USER_IDS", "").split(",")
        if x.strip().isdigit()
    ]
    ADMIN_IDS: list[int] = [
        int(x.strip())
        for x in os.getenv("ADMIN_IDS", "").split(",")
        if x.strip().isdigit()
    ]


config = Config()
