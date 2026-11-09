"""Stand-ins for Telethon's client and events, and for ARQ, so handlers run
without Telegram or the network."""
import asyncio
import itertools
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

from telethon.errors import RPCError
from telethon.tl.types import MessageMediaPhoto

from luna.arq import LunaError

BOT = SimpleNamespace(id=999, username="LunaTestBot")
USER_ID = 42
GROUP_ID = -1001234567890
GROUP_TITLE = "Andheri Gang"
SENT_AT = datetime(2026, 11, 9, 15, 44, tzinfo=timezone.utc)
# Message ids, far from the small ids that tests pick for replied messages
_message_ids = itertools.count(1000)


def rpc_error(message="CHAT_WRITE_FORBIDDEN"):
    return RPCError(None, message, 403)


@dataclass
class FakeReplyHeader:
    """telethon.tl.types.MessageReplyHeader, the fields the bot reads"""

    reply_to_msg_id: Optional[int] = None
    reply_to_top_id: Optional[int] = None
    reply_to_peer_id: Optional[object] = None
    forum_topic: bool = False


@dataclass
class FakeMessage:
    message: str = ""
    media: Optional[object] = None
    mentioned: bool = False
    reply_to: Optional[FakeReplyHeader] = None
    sender_id: Optional[int] = USER_ID
    id: int = field(default_factory=lambda: next(_message_ids))
    date: datetime = SENT_AT
    # A file: SimpleNamespace(mime_type=..., size=...)
    document: Optional[object] = None
    sticker: bool = False

    @property
    def photo(self):
        """Like Telethon's Message.photo: set for photo messages"""
        return self.media if isinstance(self.media, MessageMediaPhoto) else None


@dataclass
class FakeEvent:
    """events.NewMessage.Event"""

    message: FakeMessage
    is_private: bool = True
    is_group: bool = False
    chat_id: int = USER_ID
    sender_id: Optional[int] = USER_ID
    sender: Optional[object] = field(default_factory=lambda: SimpleNamespace(first_name="Ravi"))
    reply_error: Optional[Exception] = None
    replies: list = field(default_factory=list)
    sent: list = field(default_factory=list)

    async def get_input_chat(self):
        return f"input-chat-{self.chat_id}"

    async def get_sender(self):
        return self.sender

    async def get_chat(self):
        return SimpleNamespace(title=GROUP_TITLE if self.is_group else None)

    async def reply(self, text, **options):
        if self.reply_error:
            raise self.reply_error
        self.replies.append((text, options))
        sent = FakeMessage(text, sender_id=BOT.id)
        self.sent.append(sent)
        return sent

    def reply_texts(self):
        return [text for text, _ in self.replies]


def private(text, **options) -> FakeEvent:
    return FakeEvent(FakeMessage(text, **options))


def group(text, sender_id=USER_ID, name="Ravi", **options) -> FakeEvent:
    return FakeEvent(
        FakeMessage(text, sender_id=sender_id, **options),
        is_private=False, is_group=True, chat_id=GROUP_ID, sender_id=sender_id,
        sender=SimpleNamespace(first_name=name),
    )


class FakeClient:
    """TelegramClient: raw requests, get_messages, event handlers"""

    def __init__(self, messages=None, request_error=None, photo_bytes=b"\xff\xd8photo", download_error=None):
        self.messages = messages or {}  # {message id: FakeMessage}
        self.request_error = request_error
        self.requests = []
        self.fetched = []
        self.handlers = []
        self.photo_bytes = photo_bytes
        self.download_error = download_error
        self.downloads = []  # ids of the messages whose media was downloaded

    async def __call__(self, request):
        self.requests.append(request)
        if self.request_error:
            raise self.request_error

    async def get_messages(self, chat, ids):
        self.fetched.append((chat, ids))
        message = self.messages.get(ids)
        if isinstance(message, Exception):
            raise message
        return message

    async def download_media(self, message, file):
        assert file is bytes
        self.downloads.append(message.id)
        if self.download_error:
            raise self.download_error
        return self.photo_bytes

    def add_event_handler(self, callback, event):
        self.handlers.append((callback, event))


class FakeArq:
    """ArqClient.luna: answers "echo: <text>", or raises `error`.
    With hold=True, every call waits until release()."""

    def __init__(self, answer=None, error: Optional[LunaError] = None, hold=False):
        self.answer = answer
        self.error = error
        self.calls = []
        self.details = []  # name, chat, chat_title, context of each call
        self.images = []  # the photo of each call, or None
        self.gate = asyncio.Event()
        if not hold:
            self.gate.set()

    def release(self):
        self.gate.set()

    async def luna(self, text, user_id, image=None, **details):
        self.calls.append((text, user_id))
        self.details.append(details)
        self.images.append(image)
        await self.gate.wait()
        if self.error:
            raise self.error
        return self.answer or f"echo: {text}"
