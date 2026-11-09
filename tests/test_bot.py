import asyncio
import unittest

from telethon.tl.types import MessageMediaPhoto, MessageMediaWebPage, WebPageEmpty

from luna.arq import BUSY_TEXT, MAX_QUERY_CHARS, UNAVAILABLE_TEXT, LunaError
from luna.bot import HELP_TEXT, MAX_MESSAGE_CHARS, REPO_TEXT, TOO_LONG_TEXT, Luna
from luna.limits import WaitingRequests
from tests.fakes import (BOT, GROUP_ID, USER_ID, FakeArq, FakeClient, FakeMessage,
                         FakeReplyHeader, group, private, rpc_error)


class LunaTestCase(unittest.IsolatedAsyncioTestCase):
    def make_luna(self, arq=None, client=None, limit=6):
        self.arq = arq or FakeArq()
        self.client = client or FakeClient()
        return Luna(self.client, self.arq, BOT, WaitingRequests(limit))


class WhoGetsAnAnswerTest(LunaTestCase):
    async def test_private_messages_are_answered_as_plain_text(self):
        luna = self.make_luna()
        event = private("  hi *there*  ")
        await luna.on_message(event)
        self.assertEqual(self.arq.calls, [("hi *there*", USER_ID)])
        self.assertEqual(event.replies, [("echo: hi *there*", {"link_preview": False, "parse_mode": None})])

    async def test_group_messages_need_the_word_luna(self):
        luna = self.make_luna()
        for text in ("Hey Luna, how are you?", "luna's turn", "what is LUNA"):
            with self.subTest(text=text):
                event = group(text)
                await luna.on_message(event)
                self.assertEqual(event.reply_texts(), [f"echo: {text}"])
        for text in ("lunar eclipse tonight", "lunatic", "good morning"):
            with self.subTest(text=text):
                event = group(text)
                await luna.on_message(event)
                self.assertEqual(event.replies, [])
        self.assertEqual(self.client.fetched, [])

    async def test_group_mentions(self):
        luna = self.make_luna()
        answered = group("@lunatestbot tell me a joke")
        flagged = group("hello", mentioned=True)
        other_bot = group("@LunaTestBotX hi")
        for event in (answered, flagged, other_bot):
            await luna.on_message(event)
        self.assertEqual(len(answered.replies), 1)
        self.assertEqual(len(flagged.replies), 1)
        self.assertEqual(other_bot.replies, [])

    async def test_group_replies_to_the_bot(self):
        client = FakeClient({1: FakeMessage("I am Luna", sender_id=BOT.id), 2: FakeMessage("me", sender_id=7)})
        luna = self.make_luna(client=client)
        to_bot = group("and you?", reply_to=FakeReplyHeader(reply_to_msg_id=1))
        to_user = group("and you?", reply_to=FakeReplyHeader(reply_to_msg_id=2))
        to_deleted = group("and you?", reply_to=FakeReplyHeader(reply_to_msg_id=3))
        for event in (to_bot, to_user, to_deleted):
            await luna.on_message(event)
        self.assertEqual(to_bot.reply_texts(), ["echo: and you?"])
        self.assertEqual((to_user.replies, to_deleted.replies), ([], []))
        self.assertEqual(client.fetched, [(f"input-chat-{GROUP_ID}", 1), (f"input-chat-{GROUP_ID}", 2),
                                          (f"input-chat-{GROUP_ID}", 3)])

    async def test_forum_topic_messages_are_not_replies(self):
        luna = self.make_luna()
        in_topic = group("hello", reply_to=FakeReplyHeader(reply_to_msg_id=50, forum_topic=True))
        quote = group("hello", reply_to=FakeReplyHeader(reply_to_msg_id=5, reply_to_peer_id=object()))
        for event in (in_topic, quote):
            await luna.on_message(event)
            self.assertEqual(event.replies, [])
        self.assertEqual(self.client.fetched, [])

    async def test_unreadable_replied_message(self):
        luna = self.make_luna(client=FakeClient({1: rpc_error("CHANNEL_PRIVATE")}))
        event = group("and you?", reply_to=FakeReplyHeader(reply_to_msg_id=1))
        with self.assertLogs("luna.bot", "WARNING"):
            await luna.on_message(event)
        self.assertEqual(event.replies, [])

    async def test_channel_posts_media_and_empty_messages_are_ignored(self):
        luna = self.make_luna()
        channel_post = private("luna")
        channel_post.is_private = False
        photo = private("luna, look", media=MessageMediaPhoto())
        empty = private("   ")
        for event in (channel_post, photo, empty):
            await luna.on_message(event)
            self.assertEqual(event.replies, [])
        self.assertEqual(self.arq.calls, [])

    async def test_a_link_preview_is_not_media(self):
        luna = self.make_luna()
        event = private("luna, read https://example.com", media=MessageMediaWebPage(WebPageEmpty(1)))
        await luna.on_message(event)
        self.assertEqual(len(event.replies), 1)

    async def test_anonymous_admins_use_the_group_as_user(self):
        luna = self.make_luna()
        await luna.on_message(group("luna hi", sender_id=None))
        self.assertEqual(self.arq.calls, [("luna hi", GROUP_ID)])


class CommandTest(LunaTestCase):
    async def test_commands(self):
        luna = self.make_luna()
        cases = {
            "/start": HELP_TEXT,
            "/help": HELP_TEXT,
            "/HELP@LunaTestBot": HELP_TEXT,
            "/repo": REPO_TEXT,
            "/repo@LunaTestBot please": REPO_TEXT,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                event = group(text)
                await luna.on_message(event)
                # Markdown (no parse_mode): the links are formatting
                self.assertEqual(event.replies, [(expected, {"link_preview": False})])

    async def test_other_commands_get_nothing_and_never_reach_luna(self):
        luna = self.make_luna()
        for text in ("/repo@OtherBot", "/luna hi", "/start@LunaChatBotX"):
            for event in (private(text), group(text)):
                with self.subTest(text=text, private=event.is_private):
                    await luna.on_message(event)
                    self.assertEqual(event.replies, [])
        self.assertEqual(self.arq.calls, [])


class AnswerTest(LunaTestCase):
    async def test_too_long(self):
        luna = self.make_luna()
        event = private("x" * (MAX_QUERY_CHARS + 1))
        await luna.on_message(event)
        self.assertEqual(event.reply_texts(), [TOO_LONG_TEXT])
        self.assertEqual(self.arq.calls, [])

    async def test_arq_errors_are_shown(self):
        luna = self.make_luna(arq=FakeArq(error=LunaError(UNAVAILABLE_TEXT)))
        event = private("hi")
        await luna.on_message(event)
        self.assertEqual(event.reply_texts(), [UNAVAILABLE_TEXT])
        self.assertEqual(luna.waiting.users, set())

    async def test_long_answers_are_cut_to_one_message(self):
        luna = self.make_luna(arq=FakeArq(answer="y" * (MAX_MESSAGE_CHARS + 50)))
        event = private("hi")
        await luna.on_message(event)
        self.assertEqual(len(event.reply_texts()[0]), MAX_MESSAGE_CHARS)

    async def test_reply_errors_are_logged_not_raised(self):
        luna = self.make_luna()
        event = private("hi")
        event.reply_error = rpc_error()
        with self.assertLogs("luna.bot", "WARNING"):
            await luna.on_message(event)

    async def test_one_open_question_per_user(self):
        arq = FakeArq(hold=True)
        luna = self.make_luna(arq=arq)
        first, second = private("one"), private("two")
        task = asyncio.create_task(luna.on_message(first))
        await asyncio.sleep(0)
        await luna.on_message(second)  # still waiting for "one": ignored
        arq.release()
        await task
        self.assertEqual(arq.calls, [("one", USER_ID)])
        self.assertEqual((first.reply_texts(), second.replies), (["echo: one"], []))
        third = private("three")
        await luna.on_message(third)
        self.assertEqual(third.reply_texts(), ["echo: three"])

    async def test_busy_when_too_many_wait(self):
        arq = FakeArq(hold=True)
        luna = self.make_luna(arq=arq, limit=1)
        waiting = asyncio.create_task(luna.on_message(group("luna one", sender_id=1)))
        await asyncio.sleep(0)
        refused = group("luna two", sender_id=2)
        await luna.on_message(refused)
        self.assertEqual(refused.reply_texts(), [BUSY_TEXT])
        arq.release()
        await waiting
        self.assertEqual(len(arq.calls), 1)


class TypingTest(LunaTestCase):
    async def answer_slowly(self, luna, event):
        """on_message while ARQ takes its time, so "typing..." gets sent"""
        task = asyncio.create_task(luna.on_message(event))
        for _ in range(5):
            await asyncio.sleep(0)
        self.arq.release()
        await task

    async def test_typing_in_the_chat_and_topic(self):
        luna = self.make_luna(arq=FakeArq(hold=True))
        await self.answer_slowly(luna, private("hi"))
        self.arq.gate.clear()
        topic_reply = group("luna hi", reply_to=FakeReplyHeader(reply_to_msg_id=8, reply_to_top_id=50,
                                                                 forum_topic=True))
        await self.answer_slowly(luna, topic_reply)
        requests = self.client.requests
        self.assertEqual([(r.peer, r.top_msg_id) for r in requests],
                         [(f"input-chat-{USER_ID}", None), (f"input-chat-{GROUP_ID}", 50)])
        self.assertEqual(topic_reply.reply_texts(), ["echo: luna hi"])

    async def test_failed_typing_keeps_the_answer(self):
        luna = self.make_luna(arq=FakeArq(hold=True), client=FakeClient(request_error=rpc_error()))
        event = private("hi")
        await self.answer_slowly(luna, event)
        self.assertEqual(len(self.client.requests), 1)
        self.assertEqual(event.reply_texts(), ["echo: hi"])

    async def test_attach(self):
        luna = self.make_luna()
        luna.attach()
        self.assertEqual(len(self.client.handlers), 1)


if __name__ == "__main__":
    unittest.main()
