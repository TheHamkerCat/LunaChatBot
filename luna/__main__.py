import asyncio
import logging
import sys

from luna.app import run
from luna.settings import SettingsError, load_settings

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

logger = logging.getLogger("luna")


def setup_logging():
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout)
    # Telethon logs every connection step and httpx every request at INFO
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main():
    setup_logging()
    try:
        settings = load_settings()
    except SettingsError as error:
        logger.error("%s", error)
        sys.exit(1)
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
