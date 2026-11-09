"""The latest messages of each group, so Luna knows what the chat is about
when someone talks to her. Kept in memory only: after a restart, the log of
each group starts empty again."""
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Optional

# Per group: what ARQ's /luna accepts
MAX_MESSAGES = 100
# Groups beyond this, least recently active first, are forgotten
MAX_GROUPS = 500
# ARQ's limits per message
MAX_TEXT_CHARS = 1000
MAX_NAME_CHARS = 64

LUNA_NAME = "Luna"
# reply_to for a message that replies to one no longer in the log
OLDER_MESSAGE = "an older message"


@dataclass(frozen=True)
class LoggedMessage:
    message_id: int
    name: str
    text: str
    time: int  # Unix seconds
    reply_to: str = ""
    is_luna: bool = False

    def for_arq(self) -> dict:
        return {
            "name": self.name,
            "text": self.text,
            "time": self.time,
            "reply_to": self.reply_to,
            "is_luna": self.is_luna,
        }


def _cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


class GroupLogs:
    def __init__(self, max_messages: int = MAX_MESSAGES, max_groups: int = MAX_GROUPS):
        self.max_messages = max_messages
        self.max_groups = max_groups
        self._logs = OrderedDict()  # chat id -> deque of LoggedMessage

    def add(self, chat_id: int, message_id: int, name: str, text: str, time: int,
            replied_id: Optional[int] = None, is_luna: bool = False):
        log = self._logs.get(chat_id)
        if log is None:
            log = deque(maxlen=self.max_messages)
            self._logs[chat_id] = log
        self._logs.move_to_end(chat_id)
        while len(self._logs) > self.max_groups:
            self._logs.popitem(last=False)

        reply_to = ""
        if replied_id is not None:
            replied = self._find(log, replied_id)
            reply_to = replied.name if replied else OLDER_MESSAGE
        log.append(LoggedMessage(
            message_id, _cut(name or "someone", MAX_NAME_CHARS), _cut(text, MAX_TEXT_CHARS),
            time, reply_to, is_luna,
        ))

    def context(self, chat_id: int, without_id: Optional[int] = None) -> list:
        """The group's log for ARQ, oldest first, without the message
        with without_id (the one Luna is answering)"""
        log = self._logs.get(chat_id, ())
        return [message.for_arq() for message in log if message.message_id != without_id]

    def text_of(self, chat_id: int, message_id: int) -> Optional[str]:
        """The logged text of a message; None when it is not in the log"""
        message = self._find(self._logs.get(chat_id, ()), message_id)
        return message.text if message else None

    def is_luna_message(self, chat_id: int, message_id: int) -> Optional[bool]:
        """Whether Luna sent that message; None when it is not in the log"""
        replied = self._find(self._logs.get(chat_id, ()), message_id)
        if replied is None:
            return None
        return replied.is_luna

    @staticmethod
    def _find(log, message_id: int) -> Optional[LoggedMessage]:
        for message in reversed(log):
            if message.message_id == message_id:
                return message
        return None
