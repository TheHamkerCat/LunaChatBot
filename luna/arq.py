import base64
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ARQ starts one /luna request per API key every 5 seconds and keeps up
# to 5 more waiting, so the last one in line waits about 25 seconds plus
# the time the model takes
TIMEOUT_SECONDS = 120
CONNECT_TIMEOUT_SECONDS = 10
# ARQ refuses longer messages, names and group titles
MAX_QUERY_CHARS = 4000
MAX_NAME_CHARS = 64
MAX_TITLE_CHARS = 128
# Photos (JPEG, PNG or WebP) ARQ accepts
MAX_IMAGE_BYTES = 10 * 1024 * 1024

# Shown in chats instead of an answer, in Luna's voice
BUSY_TEXT = "ugh too many people texting me rn, try again in a min"
UNAVAILABLE_TEXT = "can't reply rn, try again in a bit"


class LunaError(Exception):
    """/luna gave no answer. The message is safe to show in chats."""


def _json_body(response: httpx.Response) -> dict:
    """The JSON object ARQ sent, or {} when it sent something else"""
    try:
        body = response.json()
    except ValueError:
        return {}
    if isinstance(body, dict):
        return body
    return {}


class ArqClient:
    def __init__(
        self,
        api_url: str,
        api_key: str,
        timeout: float = TIMEOUT_SECONDS,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        # transport: tests pass an httpx.MockTransport instead of the network
        self._client = httpx.AsyncClient(
            base_url=api_url.rstrip("/"),
            headers={"X-API-KEY": api_key},
            timeout=httpx.Timeout(timeout, connect=CONNECT_TIMEOUT_SECONDS),
            transport=transport,
        )

    async def close(self):
        await self._client.aclose()

    async def luna(self, text: str, user_id: int, name: str = "", chat: str = "",
                   chat_title: str = "", context=(), image: Optional[bytes] = None) -> str:
        """Luna's answer to text. ARQ remembers the conversation per
        user_id (and API key); 0 means no memory. name: the user's first
        name; chat: "private" or "group"; context: the group's latest
        messages (see group_log.py), used for this answer only. image: a
        photo she sees with the text (which may then be empty)."""
        payload = {
            "query": text,
            "id": user_id,
            "name": name[:MAX_NAME_CHARS],
            "chat": chat,
            "chat_title": chat_title[:MAX_TITLE_CHARS],
            "context": list(context),
        }
        if image:
            payload["image"] = base64.b64encode(image).decode()
        try:
            response = await self._client.post("luna", json=payload)
        except httpx.HTTPError as error:
            # Connection problems and timeouts
            logger.warning("Can't reach ARQ: %s", type(error).__name__)
            raise LunaError(UNAVAILABLE_TEXT) from error

        body = _json_body(response)
        result = body.get("result")
        if response.status_code == 429:
            raise LunaError(BUSY_TEXT)
        if response.status_code in (401, 403):
            logger.error("ARQ does not accept ARQ_API_KEY. Get a new key from @ARQRobot.")
            raise LunaError(UNAVAILABLE_TEXT)

        answered = response.status_code < 400 and body.get("ok") is True
        if not answered or not isinstance(result, str) or not result.strip():
            # ARQ's error text is about the request, never the user's message.
            # A refused request body (HTTP 422) comes as "detail".
            logger.warning("ARQ /luna failed: HTTP %s, %r", response.status_code,
                           result if result is not None else body.get("detail"))
            raise LunaError(UNAVAILABLE_TEXT)
        return result.strip()
