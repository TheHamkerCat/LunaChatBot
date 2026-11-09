"""Text checks that decide what the bot does with a message.
No Telegram calls here, see luna/bot.py for those."""
import re
from typing import Optional

# Group messages with this word go to Luna. "lunar" and "lunatic" don't count.
TRIGGER_WORD = re.compile(r"\bluna\b", re.IGNORECASE)
# "/name" or "/name@SomeBot", then the end or a space
COMMAND = re.compile(r"^/([A-Za-z0-9_]+)(?:@([A-Za-z0-9_]+))?(?:\s|$)")
# Name used by command_name() for commands meant for another bot
OTHER_BOT = ""


def command_name(text: str, bot_username: str) -> Optional[str]:
    """The lowercase command name ("/Help@ThisBot hi" -> "help").
    None when the text is not a command, OTHER_BOT when it ends with
    another bot's username."""
    match = COMMAND.match(text)
    if not match:
        return None
    name, target = match.groups()
    if target and target.lower() != bot_username.lower():
        return OTHER_BOT
    return name.lower()


def calls_luna(text: str, bot_username: str) -> bool:
    """The text says "Luna" or mentions @bot_username"""
    if TRIGGER_WORD.search(text):
        return True
    mention = re.compile(rf"@{re.escape(bot_username)}\b", re.IGNORECASE)
    return mention.search(text) is not None


def topic_id(reply_to) -> Optional[int]:
    """The forum topic a message (with this reply_to header) is in.
    None outside forum topics, and in a forum's General topic."""
    if reply_to is None or not getattr(reply_to, "forum_topic", False):
        return None
    # A reply inside a topic points at the replied message; reply_to_top_id
    # is then the topic. Other messages point at the topic itself.
    return reply_to.reply_to_top_id or reply_to.reply_to_msg_id


def replied_message_id(reply_to) -> Optional[int]:
    """ID of the message that a message (with this reply_to header) replies
    to, in the same chat. None for normal messages, for quotes of other
    chats, and for messages in forum topics that only name their topic."""
    if reply_to is None or getattr(reply_to, "reply_to_peer_id", None) is not None:
        return None
    # In a topic, every message points at the topic's first message;
    # a real reply there also has reply_to_top_id
    only_topic = getattr(reply_to, "forum_topic", False) and reply_to.reply_to_top_id is None
    if only_topic:
        return None
    return reply_to.reply_to_msg_id
