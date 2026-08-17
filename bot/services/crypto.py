import base64
import hashlib
import json
import random
import string

from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA

WEAPI_NONCE = "0CoJUm6Qyw8W8jud"
WEAPI_IV = b"0102030405060708"
WEAPI_MODULUS = (
    "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7"
)
WEAPI_PUBKEY = "010001"

EAPI_KEY = b"e82ckenh8dichen8"
EAPI_SALT = "36cd479b6b5"


def _aes_cbc_encrypt(text: str, key: str) -> str:
    pad_count = 16 - len(text) % 16
    text += chr(pad_count) * pad_count
    cipher = AES.new(key.encode(), AES.MODE_CBC, WEAPI_IV)
    return base64.b64encode(cipher.encrypt(text.encode())).decode()


def _rsa_encrypt(text: str) -> str:
    key = RSA.construct((int(WEAPI_MODULUS, 16), int(WEAPI_PUBKEY, 16)))
    cipher = PKCS1_v1_5.new(key)
    return base64.b64encode(cipher.encrypt(text.encode())).decode()


def _aes_ecb_encrypt(data: bytes, key: bytes) -> bytes:
    pad_count = 16 - len(data) % 16
    data += bytes([pad_count]) * pad_count
    cipher = AES.new(key, AES.MODE_ECB)
    return cipher.encrypt(data)


def weapi_params(payload: dict) -> dict[str, str]:
    text = json.dumps(payload, ensure_ascii=False)
    sec_key = "".join(
        random.choices(string.ascii_letters + string.digits, k=16)
    )
    params = _aes_cbc_encrypt(_aes_cbc_encrypt(text, WEAPI_NONCE), sec_key)
    enc_sec_key = _rsa_encrypt(sec_key)
    return {"params": params, "encSecKey": enc_sec_key}


def eapi_params(url_path: str, payload: dict) -> str:
    path = url_path.split("?", 1)[0]
    if path.startswith("/eapi/"):
        path = "/api/" + path[len("/eapi/") :]
    payload_str = json.dumps(payload, ensure_ascii=False)
    digest = hashlib.md5(f"nobody{path}use{payload_str}md5forencrypt".encode()).hexdigest()
    data = f"{path}-{EAPI_SALT}-{payload_str}-{EAPI_SALT}-{digest}"
    return _aes_ecb_encrypt(data.encode(), EAPI_KEY).hex()
