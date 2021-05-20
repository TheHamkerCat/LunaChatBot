import asyncio
import re
import pyrogram
from pyrogram import Client, filters, idle
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup
)


bot = Client(
    ":memory:",
    bot_token=🤣,
    api_id=7,
    api_hash="j",
)

@bot.on_message(filters.command(['start']))
def start(client, message):
            message.reply_text(text =f"Hello \n\n Welcome, use /help for more commnad",reply_to_message_id = message.message_id , reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Support 🇮🇳" ,url="https://t.me/Anime_SpotFlix/30") ],
                 [InlineKeyboardButton("Subscribe 🧐", url="https://t.me/Anime_SpotFlix/130") ]
           ]
        ) )

bot.start()

print(
    """
Kira Pagal Hai sabse bara wala
"""
)

idle()
