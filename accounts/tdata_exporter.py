# Copyright (c) 2026 秦屿泊 (@qinyubo)
# SPDX-License-Identifier: MIT

"""Best-effort Telethon .session -> Telegram Desktop tdata folder converter.

The tdata layout and crypto follow the same format as opentele's
``opentele.td`` (``TDesktop.SaveTData`` with ``kPerformanceMode``), which is
compatible with the official Telegram Desktop client.  The converter is
self-contained: it only needs a Telethon session SQLite file plus the
standard library and ``cryptography`` (for raw AES-ECB primitives used to
implement AES-IGE locally).

If anything goes wrong the caller should fall back to sending the plain
``.session`` file instead of aborting the whole login flow.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

APP_VERSION = 3004000
TDF_MAGIC = b"TDF$"

# account data name key: int.from_bytes(md5("data")[:8], "little")
# md5("data") hex = 8d777f385d3dfec8815d20f7496026dc, so the key is
# 0xC8FE3D5D387F778D and ToFilePart(key) == "D877F783D5D3EF8C".
DATA_NAME_KEY = 0xC8FE3D5D387F778D
# ToFilePart(data_name_key) == "D877F783D5D3EF8C"
ACCOUNT_DIR_NAME = "D877F783D5D3EF8C"
SETTINGS_KEY = 1851671142505648812
LSK_USER_SETTINGS = 0x09
MTP_AUTHORIZATION = 0x4B

# Performance-mode local key material shared by opentele's kPerformanceMode.
# Kept constant so the whole key_data file is reproducible across exports.
_LOCAL_KEY = (
    b"\xd8\x74\x59\x44\x51\x9e\x0d\x2d\x71\x30\x9d\x6c\x8d\x27\x2d\xc6"
    b"\x49\x48\xf5\xe3\xeb\xa7\x68\x53\x24\xd5\xc6\x91\xad\x81\x0c\x20"
    b"\x3b\x31\xd1\x9d\x29\xae\xd6\xac\x33\xc0\x14\xbe\x6e\x09\x84\x32"
    b"\x93\xf6\xfa\x32\xdb\xe4\x2b\x6a\x04\xe0\x04\x81\xfa\xe9\x95\x11"
    b"\x4c\xaf\x63\x42\xbd\x98\xe9\x6d\x29\x3d\xd0\x62\xc4\x58\x68\x9b"
    b"\x3a\xbd\x23\xa5\xcf\x23\x0c\x75\x52\x7c\x05\xbf\x5f\x90\xf3\x8c"
    b"\xd9\x39\x52\xcf\x61\xaa\xac\x1c\xfe\xaa\xe4\x60\x85\x92\xe3\x63"
    b"\xde\xd3\x5f\x8d\x8c\x45\x23\x4d\xef\x53\x23\x1d\xec\xb3\x55\x92"
    b"\xaf\xc4\x0d\x06\x01\xbb\xed\x11\x09\x09\x69\xf7\x4d\x9a\xb0\xcc"
    b"\x97\x82\x75\x46\xf4\x41\x24\x2d\x2c\xfb\x8e\x05\xa0\x61\x0e\x97"
    b"\x66\x9c\x0d\xa1\xad\xcc\xb5\x6e\x39\xe1\x0c\x69\xe2\x94\x23\x87"
    b"\xff\x49\x22\xf8\xc5\x5d\xcb\x88\x90\xe3\x45\xef\x31\x82\x66\xf4"
    b"\xb3\x83\x14\x30\xea\x21\x0c\x86\x3c\x17\x62\x4c\x04\x94\xcd\xea"
    b"\xd8\x1f\x52\x34\x30\xb5\xf7\x4c\x15\xda\x32\x3d\x76\x6b\xd0\x1c"
    b"\xb5\xb8\x8b\x9d\x2a\x73\x1f\x6d\x85\x33\x80\xad\x30\x6a\x86\x47"
    b"\xfa\x61\x4c\xc4\x01\x7f\x08\x90\x2c\x1e\x1f\x99\x7e\xe1\x2e\x3c"
)
_PASSCODE_KEY_SALT = (
    b"\xae\xd1\xe0\x82\x99\x42\x81\xd9\x75\x76\x0e\x72\x95\x60\xd2\xc8"
    b"\xd0\x08\xf2\xa9\xdd\x3f\xf4\xd8\x32\x45\xe2\x2e\xed\xb6\x67\x16"
)
_PASSCODE_KEY_ENCRYPTED = (
    b"\x97\xdf\x0c\xd2\xe3\x10\x91\x49\xb7\x7b\x52\x87\x99\x4d\x9c\x1c"
    b"\xa2\x40\xc5\x1e\x87\x48\x8e\x79\xdd\x02\x9b\xea\x65\xfb\x9d\x27"
    b"\x89\xbb\x5a\xbc\xfe\x65\xe8\x71\xd7\x52\xbd\x93\x8d\x83\x31\x3c"
    b"\x79\x4c\x89\x93\xa7\x34\xce\x12\x16\xf2\xe6\x60\x47\x3f\x31\x43"
    b"\xaf\x9a\x33\x36\x10\xa1\x79\x95\x87\x6e\x17\x21\xce\x1f\x61\x1d"
    b"\x1c\x69\xd8\xc1\xa2\xf5\x9f\x94\x93\x11\x97\x04\x27\x4e\x2c\xb5"
    b"\xf3\x6c\x20\xdf\x43\x9d\x15\x6d\xef\xf7\xa3\x43\x71\xdc\x44\xbc"
    b"\x86\xf8\x73\x0c\xeb\xf9\xb0\x28\xeb\x7a\x1e\xd6\x62\x1d\x99\xad"
    b"\xb6\x2b\x3b\x2c\xf2\x29\x5d\xbb\xb2\x4b\xf1\x32\xd3\x7f\xff\xc1"
    b"\x7a\x0b\xdc\xcc\x84\xbb\xea\x6e\xa3\x47\x37\xa2\x36\xb5\x82\x48"
    b"\xa7\xab\x4c\x14\x36\x3c\x20\x54\x1c\xb4\x53\x38\x67\x7f\x33\x97"
    b"\x82\xb2\x05\xe3\x55\x18\x96\x58\xdd\x45\xea\x3e\x80\x05\xf8\x51"
    b"\x14\x8e\x7e\x15\xf4\x31\x90\x4f\xa7\x9c\x68\x27\xee\x42\x6d\x3a"
    b"\xb9\xcb\xa9\x36\xeb\x33\xd4\x85\xdb\x88\xa6\xf0\xff\x97\x22\xa6"
    b"\xd6\x2f\xf7\x88\x34\x7e\x27\xc8\x2e\x9e\x13\x9e\xb0\x3a\xe5\x21"
    b"\x53\x9b\xf3\xd3\x63\xb4\xba\xea\x76\xe5\xe8\x84\xcf\x66\xfe\x6b"
    b"\xcd\x8a\x9e\x08\x9d\x36\x40\x5d\xb9\x9d\x01\xdb\x20\x46\x4f\xb6"
    b"\xca\xbb\xdc\xe4\xf6\x7e\x4e\xc3\x74\x2f\x91\x3a\x1d\xd2\xda\xc5"
)


def _u32be(value: int) -> bytes:
    return (value & 0xFFFFFFFF).to_bytes(4, "big")


def _i32be(value: int) -> bytes:
    return int(value).to_bytes(4, "big", signed=True)


def _i64be(value: int) -> bytes:
    return int(value).to_bytes(8, "big", signed=True)


def _u64be(value: int) -> bytes:
    return (value & 0xFFFFFFFFFFFFFFFF).to_bytes(8, "big")


def _qbytearray(data: bytes) -> bytes:
    """QDataStream ``<< QByteArray`` payload (uint32 length + raw bytes)."""
    return _u32be(len(data)) + data


def _aes_ige_encrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-256-IGE encryption implemented on top of raw AES-ECB."""
    if len(data) % 16 != 0:
        raise ValueError("IGE input must be a multiple of 16 bytes")
    blocks = len(data) // 16
    prev_cipher = iv[:16]
    prev_plain = iv[16:]
    out = bytearray()
    for index in range(blocks):
        block = data[index * 16 : (index + 1) * 16]
        tmp = bytes(a ^ b for a, b in zip(block, prev_cipher))
        encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
        encrypted = encryptor.update(tmp) + encryptor.finalize()
        block = bytes(a ^ b for a, b in zip(encrypted, prev_plain))
        out.extend(block)
        prev_cipher = block
        prev_plain = data[index * 16 : (index + 1) * 16]
    return bytes(out)


def _prepare_aes_oldmtp(auth_key: bytes, msg_key: bytes):
    """Derive AES key/iv the same way MTProto's ``prepare_aes_oldmtp`` does."""
    x = 8
    sha1_a = hashlib.sha1(msg_key + auth_key[x : x + 32]).digest()
    sha1_b = hashlib.sha1(
        auth_key[x + 32 : x + 48] + msg_key + auth_key[x + 48 : x + 64]
    ).digest()
    sha1_c = hashlib.sha1(auth_key[x + 64 : x + 96] + msg_key).digest()
    sha1_d = hashlib.sha1(msg_key + auth_key[x + 96 : x + 128]).digest()
    aes_key = sha1_a[:8] + sha1_b[8:20] + sha1_c[4:16]
    aes_iv = sha1_a[8:20] + sha1_b[:8] + sha1_c[16:20] + sha1_d[:8]
    return aes_key, aes_iv


def _encrypt_local(data: bytes, local_key: bytes) -> bytes:
    """EncryptedDescriptor used by opentele's ``Storage.PrepareEncrypted``."""
    size = len(data)
    full_size = size
    if full_size & 0x0F:
        full_size += 0x10 - (full_size & 0x0F)
    to_encrypt = data[:4] + bytes(full_size - 4)
    to_encrypt = size.to_bytes(4, "little") + to_encrypt[4:]
    msg_key = hashlib.sha1(to_encrypt).digest()[:16]
    aes_key, aes_iv = _prepare_aes_oldmtp(local_key, msg_key)
    return msg_key + _aes_ige_encrypt(to_encrypt, aes_key, aes_iv)


def _tdf_file(segments: list[bytes]) -> bytes:
    """Serialize a tdata file: magic, version, data segments, md5 checksum."""
    stream = bytearray()
    md5_input = bytearray()
    full_size = 0
    for data in segments:
        length = _u32be(len(data))
        stream += length + data
        md5_input += length + data
        full_size += 4 + len(data)
    md5_input += full_size.to_bytes(4, "little")
    md5_input += APP_VERSION.to_bytes(4, "little")
    md5_input += TDF_MAGIC
    checksum = hashlib.md5(md5_input).digest()
    return TDF_MAGIC + APP_VERSION.to_bytes(4, "little") + bytes(stream) + checksum


def read_session_data(session_path: str, user_id: int = None) -> dict:
    """Read (dc_id, auth_key, user_id) from a Telethon SQLite session file."""
    if not os.path.exists(session_path):
        raise FileNotFoundError(session_path)
    connection = sqlite3.connect(f"file:{session_path}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT dc_id, auth_key FROM sessions LIMIT 1"
        ).fetchone()
        if not row or not row[1]:
            raise ValueError("session has no auth_key")
        dc_id, auth_key = int(row[0]), bytes(row[1])
        found_user_id = user_id
        if found_user_id is None:
            entity = connection.execute(
                "SELECT id FROM entities WHERE id > 0 ORDER BY id LIMIT 1"
            ).fetchone()
            if entity:
                found_user_id = int(entity[0])
        return {
            "dc_id": dc_id,
            "auth_key": auth_key,
            "user_id": found_user_id,
        }
    finally:
        connection.close()


def _serialize_mtp_authorization(dc_id: int, user_id: int, auth_key: bytes) -> bytes:
    payload = bytearray()
    payload += _i64be(-1)
    payload += _i64be(user_id or 0)
    payload += _i32be(dc_id)
    payload += _i32be(1)
    payload += _i32be(dc_id)
    payload += auth_key
    payload += _i32be(0)
    return bytes(payload)


def convert_session_to_tdata(
    session_path: str,
    output_dir: str,
    user_id: int = None,
) -> str:
    """Convert a Telethon session file into a Telegram Desktop tdata folder.

    Returns the path to the created ``tdata`` directory.
    """
    data = read_session_data(session_path, user_id=user_id)
    dc_id = data["dc_id"]
    auth_key = data["auth_key"]
    user_id = data["user_id"]
    if len(auth_key) != 256:
        raise ValueError(f"invalid auth_key length: {len(auth_key)}")

    os.makedirs(output_dir, exist_ok=True)

    key_data_file = _tdf_file(
        [
            _PASSCODE_KEY_SALT,
            _PASSCODE_KEY_ENCRYPTED,
            _encrypt_local(_i32be(1) + _i32be(0) + _i32be(0), _LOCAL_KEY),
        ]
    )
    with open(os.path.join(output_dir, "key_data"), "wb") as stream:
        stream.write(key_data_file)

    maps_file = _tdf_file(
        [
            b"",
            b"",
            _encrypt_local(_u32be(LSK_USER_SETTINGS) + _u64be(SETTINGS_KEY), _LOCAL_KEY),
        ]
    )
    account_dir = os.path.join(output_dir, ACCOUNT_DIR_NAME)
    os.makedirs(account_dir, exist_ok=True)
    with open(os.path.join(account_dir, "maps"), "wb") as stream:
        stream.write(maps_file)

    serialized = _serialize_mtp_authorization(dc_id, user_id, auth_key)
    auth_file = _tdf_file(
        [
            _encrypt_local(
                _i32be(MTP_AUTHORIZATION) + _qbytearray(serialized), _LOCAL_KEY
            ),
        ]
    )
    with open(os.path.join(output_dir, f"{ACCOUNT_DIR_NAME}s"), "wb") as stream:
        stream.write(auth_file)

    return output_dir
