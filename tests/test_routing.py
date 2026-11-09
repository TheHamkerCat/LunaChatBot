import unittest

from luna.routing import OTHER_BOT, calls_luna, command_name, replied_message_id, topic_id
from tests.fakes import FakeReplyHeader

BOT = "LunaTestBot"


class CommandNameTest(unittest.TestCase):
    def test_names(self):
        cases = {
            "/help": "help",
            "/HELP": "help",
            "/help@lunatestbot": "help",
            "/repo now": "repo",
            "/repo\nnow": "repo",
            "/repo@OtherBot": OTHER_BOT,
            "/repository": "repository",
            "hello /help": None,
            "/": None,
            "/help@": None,
            "luna": None,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(command_name(text, BOT), expected)


class CallsLunaTest(unittest.TestCase):
    def test_trigger_word(self):
        for text in ("luna", "Hi LUNA!", "luna's", "(luna)", "ok luna\nhow"):
            with self.subTest(text=text):
                self.assertTrue(calls_luna(text, BOT))
        for text in ("lunar", "lunatic", "aluna", "moon"):
            with self.subTest(text=text):
                self.assertFalse(calls_luna(text, BOT))

    def test_mention(self):
        # The bot's username contains "Luna" but not the word "luna"
        self.assertTrue(calls_luna("@LunaTestBot hi", BOT))
        self.assertTrue(calls_luna("hi @lunatestbot", BOT))
        self.assertFalse(calls_luna("@LunaTestBot2 hi", BOT))
        self.assertTrue(calls_luna("@a.b hi", "a.b"))  # username is escaped
        self.assertFalse(calls_luna("@axb hi", "a.b"))


class ReplyHeaderTest(unittest.TestCase):
    def test_replied_message_id(self):
        self.assertIsNone(replied_message_id(None))
        self.assertEqual(replied_message_id(FakeReplyHeader(reply_to_msg_id=5)), 5)
        # Quote of another chat's message
        self.assertIsNone(replied_message_id(FakeReplyHeader(reply_to_msg_id=5, reply_to_peer_id=object())))
        # Plain message in a forum topic, then a reply inside it
        self.assertIsNone(replied_message_id(FakeReplyHeader(reply_to_msg_id=50, forum_topic=True)))
        self.assertEqual(
            replied_message_id(FakeReplyHeader(reply_to_msg_id=8, reply_to_top_id=50, forum_topic=True)), 8)

    def test_topic_id(self):
        self.assertIsNone(topic_id(None))
        self.assertIsNone(topic_id(FakeReplyHeader(reply_to_msg_id=5)))
        self.assertEqual(topic_id(FakeReplyHeader(reply_to_msg_id=50, forum_topic=True)), 50)
        self.assertEqual(topic_id(FakeReplyHeader(reply_to_msg_id=8, reply_to_top_id=50, forum_topic=True)), 50)


if __name__ == "__main__":
    unittest.main()
