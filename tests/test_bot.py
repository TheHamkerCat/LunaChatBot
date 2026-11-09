import asyncio
import unittest
from types import SimpleNamespace

from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto, MessageMediaWebPage, WebPageEmpty

from luna.arq import BUSY_TEXT, MAX_QUERY_CHARS, UNAVAILABLE_TEXT, LunaError
from luna.bot import (HELP_TEXT, MAX_MESSAGE_CHARS, PHOTO_FAILED_TEXT, REPO_TEXT, TOO_LONG_TEXT, Luna,
                      loggable_text)
from luna.limits import WaitingRequests
from tests.fakes import (BOT, GROUP_ID, GROUP_TITLE, SENT_AT, USER_ID, FakeArq, FakeClient, FakeEvent, FakeMessage,
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

    async def test_quotes_only_in_groups(self):
        luna = self.make_luna()
        in_private, in_group = private("hi"), group("hi luna")
        await luna.on_message(in_private)
        await luna.on_message(in_group)
        await luna.on_message(private("/help"))
        self.assertEqual(in_private.quoted, [False])
        self.assertEqual(in_group.quoted, [True])

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
        # Media other than photos (here a video file); photos are answered (PhotoTest)
        video = private("luna, look", media=MessageMediaDocument(),
                        document=SimpleNamespace(mime_type="video/mp4", size=1000))
        empty = private("   ")
        for event in (channel_post, video, empty):
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


class GroupContextTest(LunaTestCase):
    async def test_luna_sees_the_group_talk(self):
        luna = self.make_luna()
        await luna.on_message(group("who's coming to the match", sender_id=7, name="Priya"))
        await luna.on_message(group("/repo"))  # commands are not talk
        photo = group("look at this", sender_id=8, name="Arjun", media=MessageMediaPhoto())
        await luna.on_message(photo)
        asked = group("luna you in?")
        await luna.on_message(asked)
        self.assertEqual(self.arq.calls, [("luna you in?", USER_ID)])
        details = self.arq.details[0]
        self.assertEqual((details["name"], details["chat"], details["chat_title"]), ("Ravi", "group", GROUP_TITLE))
        self.assertEqual([(m["name"], m["text"]) for m in details["context"]],
                         [("Priya", "who's coming to the match"), ("Arjun", "[photo] look at this")])

    async def test_luna_remembers_what_she_said(self):
        luna = self.make_luna(arq=FakeArq(answer="obviously, i'm the carry"))
        first = group("luna you in?")
        await luna.on_message(first)
        # Replying to her answer needs no Telegram request: it is in the log
        reply = group("you're gold lol", sender_id=7, name="Priya",
                      reply_to=FakeReplyHeader(reply_to_msg_id=first.sent[0].id))
        await luna.on_message(reply)
        self.assertEqual(self.client.fetched, [])
        self.assertEqual(len(self.arq.calls), 2)
        context = self.arq.details[1]["context"]
        self.assertEqual(context[-1], {"name": "Luna", "text": "obviously, i'm the carry",
                                       "time": int(SENT_AT.timestamp()), "reply_to": "Ravi", "is_luna": True})

    async def test_private_chats_send_no_log(self):
        luna = self.make_luna()
        await luna.on_message(private("heyy"))
        self.assertEqual(self.arq.details, [{"name": "Ravi", "chat": "private"}])
        self.assertEqual(luna.logs.context(USER_ID), [])

    def test_media_labels(self):
        cases = [
            (SimpleNamespace(message="lol", media=MessageMediaPhoto(), sticker=True,
                             file=SimpleNamespace(emoji="😂")), "[sticker 😂] lol"),
            (SimpleNamespace(message="", media=MessageMediaPhoto(), gif=True, document=True), "[gif]"),
            (SimpleNamespace(message="", media=MessageMediaPhoto(), voice=True, document=True), "[voice message]"),
            (SimpleNamespace(message="vote", media=MessageMediaPhoto(),
                             poll=SimpleNamespace(poll=SimpleNamespace(question=SimpleNamespace(text="pizza?")))),
             "[poll: pizza?] vote"),
            (SimpleNamespace(message="", media=MessageMediaPhoto()), "[media]"),
            (SimpleNamespace(message="see https://x.y", media=MessageMediaWebPage(WebPageEmpty(1))),
             "see https://x.y"),
        ]
        for message, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(loggable_text(message), expected)


def image_file(mime_type="image/png", size=2_000_000):
    return {"media": MessageMediaDocument(), "document": SimpleNamespace(mime_type=mime_type, size=size)}


class PhotoTest(LunaTestCase):
    async def test_photo_in_private_chat(self):
        luna = self.make_luna()
        event = private("", media=MessageMediaPhoto())
        await luna.on_message(event)
        self.assertEqual(self.arq.calls, [("", USER_ID)])
        self.assertEqual(self.arq.images, [b"\xff\xd8photo"])
        self.assertEqual(self.client.downloads, [event.message.id])

    async def test_group_photo_needs_luna(self):
        luna = self.make_luna()
        plain = group("my new car", media=MessageMediaPhoto())
        asked = group("luna rate my fit", media=MessageMediaPhoto())
        await luna.on_message(plain)
        await luna.on_message(asked)
        self.assertEqual(self.arq.calls, [("luna rate my fit", USER_ID)])
        self.assertEqual(self.client.downloads, [asked.message.id])
        self.assertEqual(self.arq.details[0]["context"][0]["text"], "[photo] my new car")

    async def test_asking_about_a_photo_by_replying_to_it(self):
        car = group("my new car", sender_id=7, name="Priya", media=MessageMediaPhoto())
        client = FakeClient({car.message.id: car.message})
        luna = self.make_luna(client=client)
        await luna.on_message(car)
        question = group("luna thoughts?", reply_to=FakeReplyHeader(reply_to_msg_id=car.message.id))
        await luna.on_message(question)
        self.assertEqual(self.arq.calls, [("luna thoughts?", USER_ID)])
        self.assertEqual(self.arq.images, [b"\xff\xd8photo"])
        self.assertEqual(client.downloads, [car.message.id])

    async def test_replying_to_a_text_message_loads_no_photo(self):
        luna = self.make_luna()
        text = group("match at 9", sender_id=7, name="Priya")
        await luna.on_message(text)
        await luna.on_message(group("luna you in?", reply_to=FakeReplyHeader(reply_to_msg_id=text.message.id)))
        self.assertEqual(self.arq.images, [None])
        self.assertEqual((self.client.fetched, self.client.downloads), ([], []))

    async def test_which_files_count_as_photos(self):
        luna = self.make_luna()
        cases = [
            (image_file(), True),
            (image_file("image/jpeg", 10 * 1024 * 1024), True),
            (image_file("image/png", 10 * 1024 * 1024 + 1), False),
            (image_file("application/pdf"), False),
            (image_file("image/gif"), False),
            ({**image_file("image/webp"), "sticker": True}, False),
            (image_file(size=0), False),
        ]
        for options, answered in cases:
            with self.subTest(options=options):
                self.arq.calls.clear()
                await luna.on_message(private("", **options))
                self.assertEqual(bool(self.arq.calls), answered)

    async def test_failed_download(self):
        client = FakeClient(download_error=asyncio.TimeoutError())
        luna = self.make_luna(client=client)
        bare = private("", media=MessageMediaPhoto())
        with self.assertLogs("luna.bot", "WARNING"):
            await luna.on_message(bare)
        self.assertEqual(bare.reply_texts(), [PHOTO_FAILED_TEXT])
        self.assertEqual(self.arq.calls, [])
        captioned = private("look at this", media=MessageMediaPhoto())
        with self.assertLogs("luna.bot", "WARNING"):
            await luna.on_message(captioned)
        self.assertEqual((self.arq.calls, self.arq.images), ([("look at this", USER_ID)], [None]))

    async def test_downloaded_size_is_checked_again(self):
        client = FakeClient(photo_bytes=b"x" * (10 * 1024 * 1024 + 1))
        luna = self.make_luna(client=client)
        event = private("", media=MessageMediaPhoto())
        await luna.on_message(event)
        self.assertEqual(event.reply_texts(), [PHOTO_FAILED_TEXT])

    async def test_at_most_two_photos_at_once(self):
        arq = FakeArq(hold=True)
        luna = self.make_luna(arq=arq)
        tasks = [asyncio.create_task(luna.on_message(FakeEvent(FakeMessage("", media=MessageMediaPhoto(),
                                                                            sender_id=user), sender_id=user,
                                                                chat_id=user)))
                 for user in (1, 2, 3)]
        for _ in range(5):
            await asyncio.sleep(0)
        self.assertEqual(len(self.client.downloads), 2)
        arq.release()
        await asyncio.gather(*tasks)
        self.assertEqual(len(self.client.downloads), 3)


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
