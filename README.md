# LunaChatBot
Telegram AI chat bot written in Python with Telethon. The answers come from the `/luna` endpoint of [ARQ](https://arq.hamker.dev), which remembers each user's conversation.

A public running instance can be found on Telegram as [@LunaChatBot](https://t.me/LunaChatBot).

## How it answers

- **Private chat:** every text message.
- **Groups:** messages that say "Luna", mention the bot, or reply to one of its messages. For "Luna" without a mention, turn off privacy mode in @BotFather: `/mybots` > your bot > Bot Settings > Group Privacy > Turn off. With privacy mode on, the bot only sees mentions, replies and commands.
- **Commands:** `/start`, `/help`, `/repo`.

ARQ starts one `/luna` request per API key every 10 seconds and keeps up to 5 more waiting. The bot keeps at most 6 open: when more people ask, it tells them to try again in a minute. Each user has at most one open question; messages they send while waiting for an answer are skipped.

## Requirements

- Docker, or Python >= 3.12 with [uv](https://docs.astral.sh/uv/)
- A [bot token](https://t.me/BotFather)
- An ARQ API key from [@ARQRobot](https://t.me/ARQRobot)

## Settings

```sh
$ git clone https://github.com/TheHamkerCat/LunaChatBot
$ cd LunaChatBot
$ cp .env.example .env
```

Edit **.env**: fill in `BOT_TOKEN` and `ARQ_API_KEY`.

## Docker

```sh
$ docker compose up -d --build
```

Tests:

```sh
$ docker compose -f compose.test.yml run --rm --build tests
```

## Run directly

```sh
$ uv sync
$ uv run --env-file .env python -m luna
```

After changing dependencies in **pyproject.toml**, update **uv.lock** (in Docker):

```sh
$ docker run --rm -v "$PWD:/app" -w /app python:3.12.16-slim-trixie sh -c "pip install -q uv==0.13.7 && uv lock"
```

## Heroku

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/TheHamkerCat/LunaChatBot/tree/master)

Heroku has no .env file: fill in the same names as Config Vars.

## Note

- For help, ask in [ProgrammersHub](https://t.me/PatheticProgrammers)
