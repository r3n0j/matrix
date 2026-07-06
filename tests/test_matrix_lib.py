import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import matrix_lib  # noqa: E402

BOTS = {
    "user_id": "772033542325927937",
    "bots": {
        "Neo": {"token": "NEO"},
        "Agent Smith": {"token": "SMITH"},
    },
}


class BotResolutionTest(unittest.TestCase):
    def test_token_of_persona(self):
        self.assertEqual(matrix_lib.bot_token("Agent Smith", BOTS), "SMITH")

    def test_token_falls_back_to_neo(self):
        self.assertEqual(matrix_lib.bot_token("The Oracle", BOTS), "NEO")

    def test_token_none_when_no_neo(self):
        self.assertIsNone(matrix_lib.bot_token("x", {"bots": {}}))

    def test_user_id(self):
        self.assertEqual(matrix_lib.bots_user_id(BOTS), "772033542325927937")


import json  # noqa: E402
from unittest import mock  # noqa: E402


class FakeResp:
    def __init__(self, payload):
        self._p = json.dumps(payload).encode()

    def read(self):
        return self._p

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class DmSendTest(unittest.TestCase):
    def test_opens_dm_then_posts_chunked(self):
        calls = []

        def fake_urlopen(req, timeout=10):
            calls.append((req.full_url, json.loads(req.data.decode()),
                          req.get_header("Authorization")))
            if req.full_url.endswith("/users/@me/channels"):
                return FakeResp({"id": "DM123"})
            return FakeResp({"id": "msg"})

        with mock.patch.object(matrix_lib.urllib.request, "urlopen", fake_urlopen):
            ok = matrix_lib.dm_send("TOK", "USER", "x" * 2500)

        self.assertTrue(ok)
        self.assertEqual(len(calls), 3)  # 1 open DM + 2 chunks
        self.assertTrue(calls[0][0].endswith("/users/@me/channels"))
        self.assertEqual(calls[0][1], {"recipient_id": "USER"})
        self.assertTrue(calls[1][0].endswith("/channels/DM123/messages"))
        self.assertEqual(calls[1][2], "Bot TOK")

    def test_no_raise_on_network_error(self):
        def boom(req, timeout=10):
            raise OSError("net down")

        with mock.patch.object(matrix_lib.urllib.request, "urlopen", boom):
            self.assertFalse(matrix_lib.dm_send("T", "U", "hi"))

    def test_missing_args(self):
        self.assertFalse(matrix_lib.dm_send("", "U", "hi"))
        self.assertFalse(matrix_lib.dm_send("T", "", "hi"))
        self.assertFalse(matrix_lib.dm_send("T", "U", ""))


if __name__ == "__main__":
    unittest.main()
