"""Helpers that mirror client-side crypto done by the Webtop web app."""
from __future__ import annotations

import base64
import json

# The Webtop web client (main.*.js, ``encryptStringToServer``) encrypts with
# AES-256-CBC + PKCS7 using this fixed key and IV, then base64-encodes the
# ciphertext (CryptoJS ``.toString()``). They are shipped in the public JS
# bundle and are not secrets.
_KEY = b"01234567890000000150778345678901"
_IV = b"6543210987654321"


def encrypt_string_to_server(value: str) -> str:
    """Encrypt ``value`` the same way the web client's ``encryptStringToServer`` does.

    The web client encrypts ``JSON.stringify(value)``, so the plaintext includes
    the surrounding double quotes.
    """
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    plaintext = json.dumps(value, ensure_ascii=False).encode("utf-8")
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(_KEY), modes.CBC(_IV)).encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode("ascii")


def encrypt_login_data(username: str, login_counter: int = 0) -> str:
    """Build the ``Data`` field of ``LoginByUserNameAndPassword``.

    The web client sends ``encryptStringToServer(username + loginCounter)``,
    where ``loginCounter`` is the number of failed attempts in the current page
    session (``0`` for the first attempt).
    """
    return encrypt_string_to_server(f"{username}{login_counter}")
