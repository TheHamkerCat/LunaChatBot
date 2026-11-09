import asyncio
import logging
import signal
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from luna.arq import ArqClient
from luna.bot import Luna

logger = logging.getLogger(__name__)

# Telethon sessions (login key + cache of users/chats the bot has seen).
# Docker keeps this folder in a volume, so a restart does not log in again.
SESSION_DIR = Path("data")


def session_path(bot_token: str) -> Path:
    """One session file per bot. A session that is already logged in
    ignores a different BOT_TOKEN, so a new token needs a new file."""
    bot_id = bot_token.split(":", 1)[0]
    return SESSION_DIR / f"luna-{bot_id}"


async def log_in(client, bot_token: str):
    """Log in, waiting it out when Telegram limits logins.

    Telegram answers too many logins with the same token with a wait time.
    Crashing would make Docker restart the bot and try again, which can make
    the wait longer, so the bot waits instead."""
    while True:
        try:
            await client.start(bot_token=bot_token)
            return
        except FloodWaitError as error:
            logger.warning(
                "Telegram allows the next login in %s seconds (too many logins "
                "with this BOT_TOKEN). The bot waits and then starts by itself.",
                error.seconds,
            )
            await asyncio.sleep(error.seconds)


def stop_on_signals(client):
    """Ctrl+C and `docker stop` disconnect cleanly instead of killing the bot"""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.ensure_future(client.disconnect()))


async def run(settings):
    SESSION_DIR.mkdir(exist_ok=True)
    client = TelegramClient(str(session_path(settings.bot_token)), settings.api_id, settings.api_hash)
    arq = ArqClient(settings.arq_api_url, settings.arq_api_key)
    try:
        await log_in(client, settings.bot_token)
        me = await client.get_me()
        Luna(client, arq, me).attach()
        stop_on_signals(client)
        logger.info("Started as @%s", me.username)
        await client.run_until_disconnected()
    finally:
        await client.disconnect()
        await arq.close()
        logger.info("Stopped")
