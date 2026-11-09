import json
import unittest

import httpx

from luna.arq import BUSY_TEXT, UNAVAILABLE_TEXT, ArqClient, LunaError

URL = "https://arq.example"
KEY = "test-key"


def client_answering(status=200, body=None, raw=None, error=None, seen=None):
    """ArqClient whose server always gives this answer. seen: list that
    gets every request."""

    def handle(request):
        if seen is not None:
            seen.append(request)
        if error:
            raise error
        content = raw if raw is not None else json.dumps(body).encode()
        return httpx.Response(status, content=content)

    return ArqClient(URL + "/", KEY, transport=httpx.MockTransport(handle))


class LunaRequestTest(unittest.IsolatedAsyncioTestCase):
    async def test_request_and_answer(self):
        seen = []
        arq = client_answering(body={"ok": True, "result": "  Hello there!  "}, seen=seen)
        self.assertEqual(await arq.luna("hi & bye?", 42), "Hello there!")
        await arq.close()
        request = seen[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.url.path, "/luna")
        self.assertEqual(dict(request.url.params), {"query": "hi & bye?", "id": "42"})
        self.assertEqual(request.headers["X-API-KEY"], KEY)

    async def test_full_queue_is_busy(self):
        arq = client_answering(429, {"ok": False, "result": "Too many requests"})
        with self.assertRaises(LunaError) as caught:
            await arq.luna("hi", 1)
        self.assertEqual(str(caught.exception), BUSY_TEXT)

    async def test_bad_key_is_logged(self):
        arq = client_answering(401, {"detail": "X-API-KEY IS INVALID"})
        with self.assertLogs("luna.arq", "ERROR") as logs, self.assertRaises(LunaError) as caught:
            await arq.luna("hi", 1)
        self.assertEqual(str(caught.exception), UNAVAILABLE_TEXT)
        self.assertNotIn(KEY, "\n".join(logs.output))

    async def test_failures_are_unavailable(self):
        cases = {
            "model busy": dict(status=503, body={"ok": False, "result": "The chat model is busy."}),
            "ok false": dict(body={"ok": False, "result": "Something went wrong."}),
            "empty answer": dict(body={"ok": True, "result": "   "}),
            "no answer": dict(body={"ok": True}),
            "not text": dict(body={"ok": True, "result": ["hi"]}),
            "not an object": dict(body=["hi"]),
            "not json": dict(status=502, raw=b"<html>Bad gateway</html>"),
            "no connection": dict(error=httpx.ConnectError("refused")),
            "timeout": dict(error=httpx.ReadTimeout("slow")),
        }
        for name, answer in cases.items():
            with self.subTest(name), self.assertLogs("luna.arq", "WARNING"), \
                    self.assertRaises(LunaError) as caught:
                await client_answering(**answer).luna("hi", 1)
            self.assertEqual(str(caught.exception), UNAVAILABLE_TEXT)

    async def test_user_text_is_not_logged(self):
        arq = client_answering(503, {"ok": False, "result": "The chat model is busy."})
        with self.assertLogs("luna.arq", "WARNING") as logs, self.assertRaises(LunaError):
            await arq.luna("my secret plans", 1)
        self.assertNotIn("secret", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
