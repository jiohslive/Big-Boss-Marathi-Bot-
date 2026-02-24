import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from config import *

print("🚀 Starting BBM Bot...")

app = Client(
    "bbm_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

mongo = MongoClient(MONGO_URI)
db = mongo[DB_NAME]
collection = db["episodes"]

print("✅ Mongo Connected")

# ---------------------------------
# INDEX CHANNEL POSTS
# ---------------------------------

@app.on_message(filters.chat(PRIVATE_CHANNEL_ID) & filters.video)
async def index_episode(client, message):
    caption = message.caption or ""

    match = re.search(r"#bbm\s+(\d+)\s+(\d+p)", caption.lower())
    if match:
        episode = int(match.group(1))
        quality = match.group(2)

        collection.update_one(
            {"episode": episode, "quality": quality},
            {"$set": {
                "episode": episode,
                "quality": quality,
                "message_id": message.id,
                "channel_id": PRIVATE_CHANNEL_ID
            }},
            upsert=True
        )

        print(f"✅ Indexed Episode {episode} {quality}")

except Exception as e: 
print("Index Error:", e)

# ---------------------------------
# SEARCH HANDLER
# ---------------------------------

@app.on_message(filters.private & filters.text)
async def search_episode(client, message):
    text = message.text.lower()

    match = re.search(r"(\d+)", text)
    if not match:
        return

    episode = int(match.group(1))

    search_msg = await message.reply(f"🔍 Searching {text}...")
    await asyncio.sleep(2)
    await search_msg.delete()

    results = list(collection.find({"episode": episode}))

    if not results:
        await message.reply("❌ Episode Not Found")
        return

    buttons = []
    for r in results:
        buttons.append([
            InlineKeyboardButton(
                r["quality"],
                callback_data=f"get_{episode}_{r['quality']}"
            )
        ])

    await message.reply(
        f"📺 Bigg Boss Marathi\nEpisode {episode} Found\n\nSelect Quality:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

  except Exception as e:
        print("Search Error:", e)

# ---------------------------------
# QUALITY CLICK HANDLER
# ---------------------------------

@app.on_callback_query(filters.regex(r"get_(\d+)_(\d+p)"))
async def send_quality(client, callback_query):
    episode = int(callback_query.matches[0].group(1))
    quality = callback_query.matches[0].group(2)

    data = collection.find_one({
        "episode": episode,
        "quality": quality
    })

    if not data:
        await callback_query.answer("File not found!", show_alert=True)
        return

    await client.forward_messages(
        chat_id=callback_query.from_user.id,
        from_chat_id=data["channel_id"],
        message_ids=data["message_id"]
    )

    await callback_query.answer("✅ Sending...")

except Exception as e:
        print("Callback Error:", e)


print("🔥 Bot Ready To Run")
app.run()
