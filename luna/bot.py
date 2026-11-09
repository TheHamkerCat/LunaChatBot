import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from telethon import events
from telethon.errors import RPCError
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.types import MessageMediaWebPage, SendMessageTypingAction

from luna.arq import BUSY_TEXT, MAX_IMAGE_BYTES, MAX_QUERY_CHARS, LunaError
from luna.group_log import LUNA_NAME, GroupLogs
from luna.limits import FULL, USER_WAITING, WaitingRequests
from luna.routing import calls_luna, command_name, replied_message_id, topic_id

logger = logging.getLogger(__name__)

# Telegram's limit for the text of one message
MAX_MESSAGE_CHARS = 4096
# Telegram shows "typing..." for about 5 seconds after each request
TYPING_EVERY_SECONDS = 4
# Images sent as files that Luna looks at, like photos (ARQ accepts these)
IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
DOWNLOAD_TIMEOUT_SECONDS = 60
# Photos downloaded and on their way to ARQ at once: each holds up to
# 10 MB, plus about twice that as base64 and JSON
MAX_PHOTOS_AT_ONCE = 2
# How the group log shows a photo (see media_label)
PHOTO_LABEL = "[photo]"

REPO_TEXT = (
    "[GitHub](https://github.com/TheHamkerCat/LunaChatBot)"
    " | [Group](https://t.me/PatheticProgrammers)"
)
HELP_TEXT = (
    "Hi, I'm Luna. Talk to me here, or add me to a group. In a group, I answer "
    "messages that say \"Luna\", mention me, or reply to one of my messages.\n\n"
    "/repo - my source code"
)
TOO_LONG_TEXT = f"bro that's an essay, keep it under {MAX_QUERY_CHARS} characters"
PHOTO_FAILED_TEXT = "ugh that pic won't load for me, send it again?"

# Commands and the text the bot replies with (Markdown)
COMMAND_REPLIES = {
    "start": HELP_TEXT,
    "help": HELP_TEXT,
    "repo": REPO_TEXT,
}


def has_media(message) -> bool:
    """Photos, stickers, files... A link preview is not media here."""
    return message.media is not None and not isinstance(message.media, MessageMediaWebPage)


def is_picture(message) -> bool:
    """A photo, or an image sent as a file (JPEG, PNG or WebP, at most
    MAX_IMAGE_BYTES as Telegram reports it). Stickers are not."""
    if getattr(message, "photo", None):
        return True
    if getattr(message, "sticker", None):
        return False
    document = getattr(message, "document", None)
    if document is None:
        return False
    size = getattr(document, "size", 0) or 0
    return getattr(document, "mime_type", None) in IMAGE_MIME_TYPES and 0 < size <= MAX_IMAGE_BYTES


def media_label(message) -> str:
    """What a media message shows, in words, for the group log"""
    if is_picture(message):
        return PHOTO_LABEL
    if getattr(message, "sticker", None):
        emoji = getattr(getattr(message, "file", None), "emoji", "") or ""
        return f"[sticker {emoji}]" if emoji else "[sticker]"
    poll = getattr(message, "poll", None)
    if poll:
        # Newer layers wrap the question in TextWithEntities
        question = getattr(poll.poll, "question", "")
        return f"[poll: {getattr(question, 'text', question)}]"
    # Most specific first: a GIF, a voice message or a video is also a document
    labels = [
        ("gif", "[gif]"), ("photo", "[photo]"), ("voice", "[voice message]"),
        ("video_note", "[video message]"), ("video", "[video]"), ("audio", "[audio]"),
        ("geo", "[location]"), ("contact", "[contact]"), ("document", "[file]"),
    ]
    for attribute, label in labels:
        if getattr(message, attribute, None):
            return label
    return "[media]"


def loggable_text(message) -> str:
    """The message as the group log shows it: its text, after a media label"""
    text = (message.message or "").strip()
    if has_media(message):
        return f"{media_label(message)} {text}".strip()
    return text


async def sender_name(event) -> str:
    """First name of the sender; a group or channel name for anonymous
    admins and channels"""
    try:
        sender = await event.get_sender()
    except RPCError:
        return ""
    if sender is None:
        return ""
    return getattr(sender, "first_name", None) or getattr(sender, "title", None) or ""


async def chat_title(event) -> str:
    try:
        chat = await event.get_chat()
    except RPCError:
        return ""
    return getattr(chat, "title", None) or ""


async def send_reply(event, text: str, **options):
    """Answer the message and return the sent message. In a group the
    answer quotes the message, so everyone sees who it is for; in a private
    chat it is a plain message, like a person texting back. Telegram errors
    (no right to write, flood wait too long) are logged instead of raised,
    and the result is None."""
    send = event.respond if event.is_private else event.reply
    try:
        return await send(text, link_preview=False, **options)
    except RPCError as error:
        logger.warning("Can't reply in chat %s: %s", event.chat_id, error)
        return None


async def keep_typing(client, chat, topic):
    """Show "typing..." in the chat (and forum topic) until cancelled"""
    request = SetTypingRequest(chat, SendMessageTypingAction(), top_msg_id=topic)
    try:
        while True:
            await client(request)
            await asyncio.sleep(TYPING_EVERY_SECONDS)
    except (RPCError, ConnectionError) as error:
        # Only a hint: the answer is still sent
        logger.debug("Can't show typing: %s", error)


@asynccontextmanager
async def typing(client, chat, topic):
    task = asyncio.create_task(keep_typing(client, chat, topic))
    try:
        yield
    finally:
        task.cancel()


class RepliedMessage:
    """The message that a message replies to, read from Telegram at most
    once (who wrote it, and whether it is a photo)"""

    def __init__(self, client, event):
        self.client = client
        self.event = event
        self.message_id = replied_message_id(event.message.reply_to)
        self.loaded = False
        self.message = None

    async def get(self):
        if self.message_id is None or self.loaded:
            return self.message
        self.loaded = True
        try:
            self.message = await self.client.get_messages(await self.event.get_input_chat(), ids=self.message_id)
        except RPCError as error:
            logger.warning("Can't read the replied message in chat %s: %s", self.event.chat_id, error)
        return self.message


class Luna:
    def __init__(self, client, arq, me, waiting: WaitingRequests = None, logs: GroupLogs = None):
        """me: the bot's own user, from client.get_me()"""
        self.client = client
        self.arq = arq
        self.bot_id = me.id
        self.username = me.username
        self.waiting = waiting or WaitingRequests()
        self.logs = logs or GroupLogs()
        self.photo_slots = asyncio.Semaphore(MAX_PHOTOS_AT_ONCE)

    def attach(self):
        self.client.add_event_handler(self.on_message, events.NewMessage(incoming=True))

    async def on_message(self, event):
        # Private chats and groups, not channel posts
        if not (event.is_private or event.is_group):
            return
        if event.is_group:
            await self.log_group_message(event)
        message = event.message
        text = (message.message or "").strip()
        picture = is_picture(message)
        # Other media (stickers, videos, voice messages...) gets no answer
        if has_media(message) and not picture:
            return
        if not text and not picture:
            return

        command = command_name(text, self.username)
        if command is not None:
            await self.run_command(event, command)
            return
        replied = RepliedMessage(self.client, event)
        if event.is_private or await self.is_for_luna(event, text, replied):
            await self.answer(event, text, replied)

    async def log_group_message(self, event):
        """Add the message to the group's log. With privacy mode on (see
        README), the bot only gets the messages sent to it."""
        message = event.message
        text = loggable_text(message)
        # Commands are for bots, not part of the talk
        if not text or text.startswith("/"):
            return
        self.logs.add(
            event.chat_id, message.id, await sender_name(event), text,
            int(message.date.timestamp()), replied_message_id(message.reply_to),
        )

    async def run_command(self, event, command: str):
        reply = COMMAND_REPLIES.get(command)
        if reply is None:
            return
        await send_reply(event, reply)

    async def is_for_luna(self, event, text: str, replied: RepliedMessage) -> bool:
        """A group message that says "Luna", mentions the bot or replies to it"""
        if event.message.mentioned or calls_luna(text, self.username):
            return True
        if replied.message_id is None:
            return False
        # The log knows the latest messages, without asking Telegram
        in_log = self.logs.is_luna_message(event.chat_id, replied.message_id)
        if in_log is not None:
            return in_log
        message = await replied.get()
        return message is not None and message.sender_id == self.bot_id

    async def answer(self, event, text: str, replied: RepliedMessage):
        """Send the text to Luna and reply with the answer"""
        if len(text) > MAX_QUERY_CHARS:
            await send_reply(event, TOO_LONG_TEXT)
            return
        # ARQ remembers the conversation per user. Anonymous group admins
        # write as the group, so they share one conversation.
        user_id = event.sender_id or event.chat_id
        status = self.waiting.add(user_id)
        if status == USER_WAITING:
            # The answer to this user's last message is still on its way
            return
        if status == FULL:
            await send_reply(event, BUSY_TEXT)
            return
        try:
            reply = await self.ask(event, text, user_id, replied)
        finally:
            self.waiting.remove(user_id)
        # Plain text: the model's * and _ are not formatting
        reply = reply[:MAX_MESSAGE_CHARS]
        sent = await send_reply(event, reply, parse_mode=None)
        if sent is not None and event.is_group:
            # Telegram does not send the bot its own messages
            self.logs.add(event.chat_id, sent.id, LUNA_NAME, reply, int(sent.date.timestamp()),
                          event.message.id, is_luna=True)

    async def ask(self, event, text: str, user_id: int, replied: RepliedMessage) -> str:
        """Luna's answer, or the reason there is none. Shows "typing..."
        in the chat while waiting."""
        chat = await event.get_input_chat()
        details = {"name": await sender_name(event), "chat": "private"}
        if event.is_group:
            details.update(
                chat="group",
                chat_title=await chat_title(event),
                context=self.logs.context(event.chat_id, without_id=event.message.id),
            )
        try:
            async with typing(self.client, chat, topic_id(event.message.reply_to)):
                if not self.may_have_picture(event, replied):
                    return await self.arq.luna(text, user_id, **details)
                # The photo bytes are held only while a slot is taken
                async with self.photo_slots:
                    image = await self.picture_for(event, replied)
                    if image is None and not text:
                        return PHOTO_FAILED_TEXT
                    return await self.arq.luna(text, user_id, image=image, **details)
        except LunaError as error:
            return str(error)

    def may_have_picture(self, event, replied: RepliedMessage) -> bool:
        """The message is a photo, or replies to a message that is or may be one"""
        if is_picture(event.message):
            return True
        if replied.message_id is None:
            return False
        if replied.loaded:
            return replied.message is not None and is_picture(replied.message)
        # The log knows the latest group messages, without asking Telegram
        logged = self.logs.text_of(event.chat_id, replied.message_id)
        return logged is None or logged.startswith(PHOTO_LABEL)

    async def picture_for(self, event, replied: RepliedMessage) -> Optional[bytes]:
        """The photo Luna sees: the message's own, or the one it replies to
        ("luna rate this"). None when there is none or it can't be loaded."""
        if is_picture(event.message):
            return await self.download(event.message)
        message = await replied.get()
        if message is None or not is_picture(message):
            return None
        return await self.download(message)

    async def download(self, message) -> Optional[bytes]:
        """The photo's bytes. is_picture() already checked the size Telegram
        reports; the downloaded size is checked again."""
        try:
            data = await asyncio.wait_for(
                self.client.download_media(message, file=bytes), DOWNLOAD_TIMEOUT_SECONDS
            )
        except (RPCError, asyncio.TimeoutError, ValueError, TypeError) as error:
            logger.warning("Can't download a photo: %s", type(error).__name__)
            return None
        if not isinstance(data, bytes) or not data or len(data) > MAX_IMAGE_BYTES:
            return None
        return data
