from asyncio import sleep, gather
import re
from aiohttp import ClientSession
from config import ARQ_API_KEY, bot_token, ARQ_API_BASE_URL
from pyrogram import Client, filters, idle
from Python_ARQ import ARQ

luna = Client(
    ":memory:",
    bot_token=bot_token,
    api_id=6,
    api_hash="eb06d4abfb49dc3eeb1aeb98ae0f581e",
)
bot_id = int(bot_token.split(":")[0])
aiohttp_session = ClientSession()
arq = ARQ(ARQ_API_BASE_URL, ARQ_API_KEY, aiohttp_session)

async def lunaQuery(query: str, user_id: int):
    luna = await arq.luna(query, user_id)
    return luna.result

async def type_and_send(message):
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    query = message.text.strip()
    await message._client.send_chat_action(chat_id, "typing")
    response, _ = await gather(lunaQuery(query, user_id), sleep(2))
    await message.reply_text(response)
    await message._client.send_chat_action(chat_id, "cancel")


@luna.on_message(filters.command("repo") & ~filters.edited)
async def repo(_, message):
    await message.reply_text(
        "[GitHub](https://github.com/thehamkercat/LunaChatBot)"
        + " | [Group](t.me/PatheticProgrammers)",
        disable_web_page_preview=True,
    )


@luna.on_message(filters.command("help") & ~filters.edited)
async def start(_, message):
    await luna.send_chat_action(message.chat.id, "typing")
    await sleep(2)
    await message.reply_text("/repo - Get Repo Link")


@luna.on_message(
    ~filters.private
    & filters.text
    & ~filters.command("help")
    & ~filters.edited,
    group=69
)
async def chat(_, message):
    if message.reply_to_message:
        if not message.reply_to_message.from_user:
            return
        from_user_id = message.reply_to_message.from_user.id
        if from_user_id != bot_id:
            return
    match = re.search("[.|\n]{0,}luna[.|\n]{0,}", message.text.strip(), flags=re.IGNORECASE)
    if not match and from_user_id != bot_id:
        return
    await type_and_send(message)


@luna.on_message(
    filters.private
    & ~filters.command("help")
    & ~filters.edited
)
async def chatpm(_, message):
    if not message.text:
        return
    await type_and_send(message)

luna.start()

print(
    """

-----------------
| Luna Started! |
-----------------
"""
)
idle()
