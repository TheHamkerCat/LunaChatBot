import unittest
from pathlib import Path

from telethon.errors import FloodWaitError

from luna.app import log_in, session_path
from luna.limits import ADDED, FULL, USER_WAITING, WaitingRequests


class FlakyLogin:
    """TelegramClient.start: Telegram says "wait" `waits` times, then logs in"""

    def __init__(self, waits):
        self.waits = waits
        self.tries = 0

    async def start(self, bot_token):
        self.tries += 1
        if self.tries <= self.waits:
            raise FloodWaitError(None, capture=0)


class AppTest(unittest.IsolatedAsyncioTestCase):
    def test_one_session_per_bot(self):
        self.assertEqual(session_path("123456:ABC"), Path("data/luna-123456"))

    async def test_log_in_waits_out_flood_limits(self):
        client = FlakyLogin(waits=2)
        with self.assertLogs("luna.app", "WARNING") as logs:
            await log_in(client, "123456:ABC")
        self.assertEqual(client.tries, 3)
        self.assertEqual(len(logs.output), 2)
        self.assertNotIn("ABC", "\n".join(logs.output))


class WaitingRequestsTest(unittest.TestCase):
    def test_limits(self):
        waiting = WaitingRequests(limit=2)
        self.assertEqual(waiting.add(1), ADDED)
        self.assertEqual(waiting.add(1), USER_WAITING)
        self.assertEqual(waiting.add(2), ADDED)
        self.assertEqual(waiting.add(3), FULL)
        waiting.remove(1)
        self.assertEqual(waiting.add(3), ADDED)
        waiting.remove(99)  # unknown: no error


if __name__ == "__main__":
    unittest.main()
