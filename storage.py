import os
import json
import config

def init_storage():
    os.makedirs(config.LOG_FOLDER, exist_ok=True)
    os.makedirs(config.SESSIONS_DIR, exist_ok=True)
    if not os.path.exists(config.WHITELIST_FILE):
        with open(config.WHITELIST_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

def load_all_whitelist():
    with open(config.WHITELIST_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_all_whitelist(data):
    with open(config.WHITELIST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, ensure_ascii=False, indent=2, fp=f)

def add_white_device(admin_uid: int, phone: str, device_name: str) -> bool:
    data = load_all_whitelist()
    key_uid = str(admin_uid)
    if key_uid not in data:
        data[key_uid] = {}
    if phone not in data[key_uid]:
        data[key_uid][phone] = []
    dev_list = data[key_uid][phone]
    if device_name in dev_list:
        return False
    dev_list.append(device_name)
    save_all_whitelist(data)
    return True

def remove_white_device(admin_uid: int, phone: str, device_name: str) -> bool:
    data = load_all_whitelist()
    key_uid = str(admin_uid)
    if key_uid not in data or phone not in data[key_uid]:
        return False
    dev_list = data[key_uid][phone]
    if device_name not in dev_list:
        return False
    dev_list.remove(device_name)
    if not dev_list:
        del data[key_uid][phone]
        if not data[key_uid]:
            del data[key_uid]
    save_all_whitelist(data)
    return True

def get_phone_whitelist(admin_uid: int, phone: str) -> list:
    data = load_all_whitelist()
    key_uid = str(admin_uid)
    if key_uid not in data or phone not in data[key_uid]:
        return []
    return data[key_uid][phone]