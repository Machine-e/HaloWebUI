"""Crypto utilities for WeChat Work and Feishu webhook verification."""

import base64
import hashlib
import struct
from typing import Optional


def wechat_work_check_signature(
    token: str, timestamp: str, nonce: str, encrypt_data: str, msg_signature: str
) -> bool:
    """Verify WeChat Work callback signature using SHA1."""
    parts = sorted([token, timestamp, nonce, encrypt_data])
    raw = "".join(parts).encode("utf-8")
    return hashlib.sha1(raw).hexdigest() == msg_signature


def wechat_work_decrypt(ciphertext_b64: str, encoding_aes_key: str) -> tuple[str, str]:
    """Decrypt a WeChat Work message.

    Args:
        ciphertext_b64: Base64-encoded ciphertext from the callback.
        encoding_aes_key: 43-char EncodingAESKey from the app config.

    Returns:
        (message_xml, receive_id) tuple.
    """
    try:
        from Crypto.Cipher import AES
    except ImportError:
        from Cryptodome.Cipher import AES

    key = base64.b64decode(encoding_aes_key + "=")
    iv = key[:16]
    ciphertext = base64.b64decode(ciphertext_b64)

    cipher = AES.new(key, AES.MODE_CBC, iv)
    plaintext = cipher.decrypt(ciphertext)

    # PKCS#7 unpad
    pad_len = plaintext[-1]
    plaintext = plaintext[:-pad_len]

    # Structure: 16-byte random + 4-byte msg_len (big-endian) + msg + receive_id
    msg_len = struct.unpack("!I", plaintext[16:20])[0]
    msg = plaintext[20 : 20 + msg_len].decode("utf-8")
    receive_id = plaintext[20 + msg_len :].decode("utf-8")

    return msg, receive_id


def wechat_work_encrypt(msg: str, encoding_aes_key: str, receive_id: str) -> str:
    """Encrypt a message for WeChat Work response (rarely needed but included for completeness).

    Returns base64-encoded ciphertext.
    """
    import os

    try:
        from Crypto.Cipher import AES
    except ImportError:
        from Cryptodome.Cipher import AES

    key = base64.b64decode(encoding_aes_key + "=")
    iv = key[:16]

    msg_bytes = msg.encode("utf-8")
    receive_id_bytes = receive_id.encode("utf-8")
    random_bytes = os.urandom(16)

    plaintext = (
        random_bytes + struct.pack("!I", len(msg_bytes)) + msg_bytes + receive_id_bytes
    )

    # PKCS#7 pad to 32-byte blocks
    block_size = 32
    pad_len = block_size - (len(plaintext) % block_size)
    plaintext += bytes([pad_len]) * pad_len

    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(plaintext)
    return base64.b64encode(ciphertext).decode("utf-8")


def feishu_decrypt(encrypt_data: str, encrypt_key: str) -> str:
    """Decrypt a Feishu event callback payload.

    Args:
        encrypt_data: The 'encrypt' field from the callback JSON.
        encrypt_key: The Encrypt Key configured in the Feishu app.

    Returns:
        Decrypted JSON string.
    """
    try:
        from Crypto.Cipher import AES
    except ImportError:
        from Cryptodome.Cipher import AES

    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    ciphertext = base64.b64decode(encrypt_data)

    iv = ciphertext[: AES.block_size]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    plaintext = cipher.decrypt(ciphertext[AES.block_size :])

    # PKCS#7 unpad
    pad_len = plaintext[-1]
    plaintext = plaintext[:-pad_len]

    return plaintext.decode("utf-8")


def feishu_verify_token(payload: dict, verification_token: str) -> bool:
    """Check that the Feishu event token matches our configured verification_token."""
    return payload.get("token") == verification_token
