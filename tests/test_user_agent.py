import asyncio
import unittest

import httpx

from webtop.client import DEFAULT_USER_AGENT, WebtopClient


def _outgoing_user_agent(client: WebtopClient) -> str:
    return client._http.build_request("GET", "/").headers["User-Agent"]


class UserAgentTests(unittest.TestCase):
    def _make(self, **kwargs) -> WebtopClient:
        client = WebtopClient("user", "pass", **kwargs)
        self.addCleanup(lambda: asyncio.run(client.close()))
        return client

    def test_default_is_browser_user_agent(self):
        ua = _outgoing_user_agent(self._make())
        self.assertEqual(ua, DEFAULT_USER_AGENT)
        self.assertNotIn("python-httpx", ua)

    def test_custom_user_agent(self):
        self.assertEqual(_outgoing_user_agent(self._make(user_agent="my-agent/1.0")), "my-agent/1.0")

    def test_none_falls_back_to_httpx_default(self):
        ua = _outgoing_user_agent(self._make(user_agent=None))
        self.assertTrue(ua.startswith("python-httpx/"), ua)

    def test_content_type_kept(self):
        client = self._make(user_agent="x")
        self.assertEqual(client._http.headers["Content-Type"], "application/json; charset=utf-8")


if __name__ == "__main__":
    unittest.main()
