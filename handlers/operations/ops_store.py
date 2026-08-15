# Copyright (c) 2026 秦屿泊 (@qinyubo)
# SPDX-License-Identifier: MIT

"""运营扩展数据存储：广播历史、工单、促销、卡密。

沿用项目统一模式：写临时文件 + os.replace 原子替换，损坏时保留备份。
"""

from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
import threading
from typing import Any, Dict, List, Optional

import settings as config

logger = logging.getLogger(__name__)

_lock = threading.RLock()

_broadcasts: Dict[str, Dict] = {}
_tickets: Dict[str, Dict] = {}
_broadcasts_loaded = False
_tickets_loaded = False


def _atomic_write(path: str, payload: Dict) -> bool:
    try:
        directory = os.path.dirname(os.path.abspath(path)) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix=os.path.basename(path) + ".", suffix=".tmp", dir=directory, text=True
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
            return True
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
    except Exception:
        logger.exception("运营数据写入失败: %s", path)
        return False


def _load_file(path: str) -> Optional[Dict]:
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("运营数据文件顶层必须是对象")
        return data
    except Exception:
        logger.exception("运营数据文件损坏: %s", path)
        try:
            backup = f"{path}.corrupt.{os.path.getmtime(path)}.backup"
            os.rename(path, backup)
            logger.info("运营数据已备份为: %s", backup)
        except OSError:
            pass
        return {}


# ---------------------------------------------------------------- 广播

def load_broadcasts() -> None:
    global _broadcasts, _broadcasts_loaded
    with _lock:
        data = _load_file(config.BROADCAST_FILE)
        _broadcasts = data or {}
        _broadcasts_loaded = True


def save_broadcasts() -> bool:
    with _lock:
        if not _atomic_write(config.BROADCAST_FILE, _broadcasts):
            return False
        return True


def add_broadcast(record: Dict) -> str:
    with _lock:
        _broadcasts.setdefault("items", [])
        _broadcasts["items"].insert(0, record)
        save_broadcasts()
        return str(record.get("id", ""))


def get_broadcast(broadcast_id: str) -> Optional[Dict]:
    with _lock:
        for item in _broadcasts.get("items") or []:
            if str(item.get("id", "")) == str(broadcast_id):
                return copy.deepcopy(item)
    return None


def save_broadcast(record: Dict) -> bool:
    with _lock:
        broadcast_id = str(record.get("id", ""))
        items = _broadcasts.setdefault("items", [])
        for index, item in enumerate(items):
            if str(item.get("id", "")) == broadcast_id:
                items[index] = copy.deepcopy(record)
                return save_broadcasts()
        items.insert(0, copy.deepcopy(record))
        return save_broadcasts()


def list_broadcasts(limit: int = 20) -> List[Dict]:
    with _lock:
        items = copy.deepcopy(_broadcasts.get("items") or [])
    return items[:limit]


# ---------------------------------------------------------------- 工单

def load_tickets() -> None:
    global _tickets, _tickets_loaded
    with _lock:
        data = _load_file(config.TICKET_FILE)
        _tickets = data or {}
        _tickets_loaded = True


def save_tickets() -> bool:
    with _lock:
        if not _atomic_write(config.TICKET_FILE, _tickets):
            return False
        return True


def list_all_tickets() -> List[Dict]:
    with _lock:
        return copy.deepcopy(list(_tickets.values()))


def get_ticket(ticket_id: str) -> Optional[Dict]:
    with _lock:
        return copy.deepcopy(_tickets.get(ticket_id))


def upsert_ticket(ticket: Dict) -> bool:
    with _lock:
        _tickets[str(ticket["id"])] = copy.deepcopy(ticket)
        return save_tickets()


def tickets_for_user(user_id: int, limit: int = 20) -> List[Dict]:
    with _lock:
        items = [
            copy.deepcopy(t)
            for t in _tickets.values()
            if int(t.get("user_id", -1)) == int(user_id)
        ]
    items.sort(key=lambda t: t.get("updated_at", ""), reverse=True)
    return items[:limit]


def next_ticket_id() -> str:
    with _lock:
        now = __import__("datetime").datetime.now()
        return f"TK-{now.strftime('%y%m%d')}-{len(_tickets) + 1:04d}"


# ---------------------------------------------------------------- 促销/卡密（存 user_data 系统设置）

def get_promotions() -> List[Dict]:
    from storage.data_manager import DataManager, user_data
    settings = user_data.get("system_settings") or {}
    return copy.deepcopy(settings.get("promotions") or [])


def set_promotions(promotions: List[Dict]) -> bool:
    from storage.data_manager import DataManager, user_data
    settings = user_data.setdefault("system_settings", {})
    settings["promotions"] = promotions
    return DataManager.save_user_data()


def active_promotion_for(plan_id: str) -> Optional[Dict]:
    now = __import__("time").time()
    for promo in get_promotions():
        if promo.get("plan_id") != plan_id:
            continue
        try:
            if float(promo["starts_at"]) <= now <= float(promo["ends_at"]):
                return copy.deepcopy(promo)
        except (KeyError, TypeError, ValueError):
            continue
    return None


def get_redeem_codes() -> Dict[str, Dict]:
    from storage.data_manager import DataManager, user_data
    settings = user_data.get("system_settings") or {}
    return copy.deepcopy(settings.get("redeem_codes") or {})


def set_redeem_codes(codes: Dict[str, Dict]) -> bool:
    from storage.data_manager import DataManager, user_data
    settings = user_data.setdefault("system_settings", {})
    settings["redeem_codes"] = codes
    return DataManager.save_user_data()
