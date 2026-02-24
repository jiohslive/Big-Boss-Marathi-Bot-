import os
import re
import asyncio
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient

# ---------------- ENV ----------------
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URL = os.environ.get("MONGO_URL")
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL"))
SERIES_CHANNEL = int(os.environ.get("SERIES_CHANNEL"))

# ---------------- INIT ----------------
mongo = MongoClient(MONGO_URL)
db = mongo["pro_serial_bot"]
episodes = db["episodes"]
users = db["users"]

app = Client("pro_serial_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ---------------- LOG ----------------
async def log(text):
    try:
        await app.send_message(LOG_CHANNEL, text)
    except:
        pass

# ---------------- START ----------------
@app.on_message(filters.private & filters.command("start"))
async def start(client, message):
    user = message.from_user

    users.update_one(
        {"user_id": user.id},
        {"$set": {
            "username": user.username,
            "first_name": user.first_name,
            "joined": datetime.utcnow()
        }},
        upsert=True
    )

    total_users = users.count_documents({})

    await message.reply(
        f"👋 Welcome {user.first_name}\n\n"
        f"🎬 Send Episode Number like:\n"
        f"55\nS06E55\nBig Boss Marathi 55\n\n"
        f"👥 Total Users: {total_users}"
    )

    await log(f"🆕 New User: @{user.username} ({user.id})")

# ---------------- SEARCH ----------------
@app.on_message(filters.private & filters.text)
async def search(client, message):
    query = message.text.lower()

    searching = await message.reply("🔍 Searching...")
    await asyncio.sleep(1)
    await searching.delete()

    ep_match = re.search(r'\d+', query)
    if not ep_match:
        await message.reply("❌ Send valid episode number.")
        return

    ep_number = int(ep_match.group())

    data = episodes.find_one({"episode": ep_number})
    if not data:
        await message.reply("❌ Episode Not Found.")
        await log(f"❌ Episode {ep_number} not found")
        return

    qualities = list(data["qualities"].keys())

    buttons = []
    for q in qualities:
        buttons.append([InlineKeyboardButton(q, callback_data=f"q_{ep_number}_{q}")])

    await message.reply(
        f"🎬 Episode {ep_number}\n\nSelect Quality 👇",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ---------------- QUALITY ----------------
@app.on_callback_query(filters.regex("^q_"))
async def quality(client, callback_query):
    data = callback_query.data.split("_")
    ep_number = int(data[1])
    quality = data[2]

    await callback_query.message.delete()

    ep_data = episodes.find_one({"episode": ep_number})
    if not ep_data:
        await callback_query.message.reply("❌ Data Missing")
        return

    msg_id = ep_data["qualities"].get(quality)

    if not msg_id:
        await callback_query.message.reply("❌ Quality Not Available")
        return

    await app.copy_message(
        chat_id=callback_query.from_user.id,
        from_chat_id=SERIES_CHANNEL,
        message_id=msg_id
    )

# ---------------- AUTO STORE ----------------
@app.on_message(filters.channel & filters.video)
async def store_episode(client, message):
    if message.chat.id != SERIES_CHANNEL:
        return

    caption = message.caption.lower() if message.caption else ""

    ep_match = re.search(r's?\d*e?(\d+)', caption)
    if not ep_match:
        await log("⚠️ Episode format not detected")
        return

    ep_number = int(ep_match.group(1))
    quality = next((q for q in ["480p","720p","1080p"] if q in caption), "480p")

    existing = episodes.find_one({"episode": ep_number})

    if existing:
        episodes.update_one(
            {"episode": ep_number},
            {"$set": {f"qualities.{quality}": message.id}}
        )
    else:
        episodes.insert_one({
            "episode": ep_number,
            "qualities": {quality: message.id},
            "added_on": datetime.utcnow()
        })

    await log(f"📥 Added Episode {ep_number} ({quality})")

# ---------------- STATS ----------------
@app.on_message(filters.private & filters.command("stats"))
async def stats(client, message):
    total_users = users.count_documents({})
    total_eps = episodes.count_documents({})

    await message.reply(
        f"📊 Bot Stats\n\n"
        f"👥 Users: {total_users}\n"
        f"🎬 Episodes: {total_eps}"
    )

# ---------------- RUN ----------------
if __name__ == "__main__":
    print("🚀 PRO BOT RUNNING...")
    app.run()
