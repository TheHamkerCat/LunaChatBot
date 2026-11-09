import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ARQ starts one /luna request per API key every 10 seconds and keeps up
# to 5 more waiting, so the last one in line can wait about a minute
TIMEOUT_SECONDS = 120
CONNECT_TIMEOUT_SECONDS = 10
# ARQ refuses longer messages
MAX_QUERY_CHARS = 4000

# Shown in chats instead of an answer
BUSY_TEXT = "Too many people are talking to me right now. Try again in a minute."
UNAVAILABLE_TEXT = "I can't answer right now. Try again later."


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

    async def luna(self, text: str, user_id: int) -> str:
        """Luna's answer to text. ARQ remembers the conversation per
        user_id (and API key); 0 means no memory."""
        try:
            response = await self._client.get("luna", params={"query": text, "id": user_id})
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
            # ARQ's error text is about the request, never the user's message
            logger.warning("ARQ /luna failed: HTTP %s, %r", response.status_code, result)
            raise LunaError(UNAVAILABLE_TEXT)
        return result.strip()
