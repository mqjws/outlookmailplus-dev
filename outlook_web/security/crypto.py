from __future__ import annotations

import base64
from typing import Optional

import bcrypt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from outlook_web import config

_cipher_suite: Optional[Fernet] = None


def hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """验证密码是否匹配哈希值"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def is_password_hashed(password: str) -> bool:
    """检查密码是否已经是 bcrypt 哈希值"""
    return password.startswith("$2b$") or password.startswith("$2a$") or password.startswith("$2y$")


def get_encryption_key() -> bytes:
    """
    从 SECRET_KEY 派生加密密钥
    使用 PBKDF2 从 SECRET_KEY 派生 32 字节密钥
    """
    secret_key = config.require_secret_key()

    # 使用固定盐（因为我们需要确保重启后能解密）
    # 注意：这里使用固定盐是为了确保密钥一致性，安全性依赖于 SECRET_KEY 的强度
    salt = b"outlook_email_encryption_salt_v1"

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))
    return key


def get_cipher() -> Fernet:
    """获取加密器实例（单例模式）"""
    global _cipher_suite
    if _cipher_suite is None:
        key = get_encryption_key()
        _cipher_suite = Fernet(key)
    return _cipher_suite


def encrypt_data(data: str) -> str:
    """
    加密敏感数据
    返回 base64 编码的加密字符串，带有 'enc:' 前缀标识
    """
    if not data:
        return data

    # 如果已经加密，直接返回
    if data.startswith("enc:"):
        return data

    cipher = get_cipher()
    encrypted = cipher.encrypt(data.encode("utf-8"))
    return "enc:" + encrypted.decode("utf-8")


def decrypt_data(encrypted_data: str) -> str:
    """
    解密敏感数据
    如果数据未加密（没有 'enc:' 前缀），直接返回原始数据
    """
    if not encrypted_data:
        return encrypted_data

    # 如果没有加密标识，返回原始数据（向后兼容）
    if not encrypted_data.startswith("enc:"):
        return encrypted_data

    try:
        cipher = get_cipher()
        encrypted_bytes = encrypted_data[4:].encode("utf-8")  # 移除 'enc:' 前缀
        decrypted = cipher.decrypt(encrypted_bytes)
        return decrypted.decode("utf-8")
    except Exception as e:
        # 解密失败，可能是密钥变更或数据损坏
        import sys

        error_msg = f"Failed to decrypt data: {str(e)}"
        print(f"[ERROR] {error_msg}", file=sys.stderr)
        print(f"[ERROR] Data preview: {encrypted_data[:50]}...", file=sys.stderr)
        print(
            "[ERROR] This usually means SECRET_KEY has changed or data is corrupted",
            file=sys.stderr,
        )
        raise RuntimeError(error_msg)


def is_encrypted(data: str) -> bool:
    """检查数据是否已加密"""
    return bool(data) and data.startswith("enc:")
