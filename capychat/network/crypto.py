"""消息加密模块：AES-256-GCM 加密/解密。

所有 TCP/UDP 消息可通过共享密码加密。不设密码时保持明文兼容。
"""

import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

ENCRYPTED_FLAG = b'\x01'
PLAINTEXT_FLAG = b'\x00'

_SALT = b'lanchat_p2p_salt_v1'   # 固定盐值，确保同密码派生同密钥


def derive_key(password: str) -> bytes:
    """从房间密码派生 AES-256 密钥（PBKDF2-SHA256）。"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=600000,
        backend=default_backend(),
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt(plaintext: bytes, key: bytes) -> bytes:
    """AES-256-GCM 加密。返回 flag(1) + nonce(12) + ciphertext_and_tag。"""
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext, None)
    return ENCRYPTED_FLAG + nonce + ct


def decrypt(data: bytes, key: bytes) -> bytes | None:
    """AES-256-GCM 解密。成功返回明文，失败返回 None。"""
    if len(data) < 13:
        return None
    try:
        nonce = data[1:13]
        ct = data[13:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None)
    except Exception:
        return None


def try_decrypt(data: bytes, key: bytes | None) -> tuple[bytes, bool]:
    """尝试解密。如果数据已加密且有 key 则解密；否则原样返回（去除标志位）。"""
    if len(data) == 0:
        return data, False
    if key and data[0:1] == ENCRYPTED_FLAG:
        plain = decrypt(data, key)
        if plain is not None:
            return plain, True
    # 明文或解密失败：去除明文标志位
    if data[0:1] == PLAINTEXT_FLAG:
        return data[1:], False
    return data, False
