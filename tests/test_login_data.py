import asyncio
import base64
import json

import httpx

from webtop import WebtopClient, encrypt_login_data
from webtop.crypto import _IV, _KEY


def _decrypt(value: str) -> str:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    decryptor = Cipher(algorithms.AES(_KEY), modes.CBC(_IV)).decryptor()
    padded = decryptor.update(base64.b64decode(value)) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")


def test_known_vector():
    # Regression vector; the web client produces the same value for this input.
    assert encrypt_login_data("someuser") == "QKsl0pDtA6UW8doeJawpYQ=="


def test_old_default_has_the_same_shape():
    # The previous hard-coded default decrypts to a JSON string of the form
    # "<username><counter>", i.e. it was one specific user's login Data.
    plain = _decrypt("+Aabe7FAdVluG6Lu+0ibrA==")
    assert plain.startswith('"') and plain.endswith('"') and plain[-2].isdigit()


def test_plaintext_is_json_stringified_username_plus_counter():
    assert _decrypt(encrypt_login_data("someuser")) == '"someuser0"'
    assert _decrypt(encrypt_login_data("someuser", 3)) == '"someuser3"'


def _login_payload(**client_kwargs):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"status": True, "data": {"token": "t"}})

    async def run():
        client = WebtopClient("someuser", "pw", **client_kwargs)
        client._http = httpx.AsyncClient(
            base_url="https://webtopserver.smartschool.co.il",
            transport=httpx.MockTransport(handler),
        )
        async with client:
            await client.login()

    asyncio.run(run())
    return seen


def test_login_computes_data_from_username_by_default():
    assert _login_payload()["Data"] == encrypt_login_data("someuser")


def test_explicit_data_still_wins():
    assert _login_payload(data="explicit")["Data"] == "explicit"
