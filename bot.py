import os
import asyncio
import re
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient

# ---------------- ENV VARIABLES ----------------
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URL = os.environ.get("MONGO_URL")
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL"))
SERIES_CHANNEL = int(os.environ.get("SERIES_CHANNEL"))

# ---------------- INIT ----------------
mongo = MongoClient(MONGO_URL)
db = mongo["serial_bot"]
episodes_col = db["episodes"]
users_col = db["users"]

app = Client("serial_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ---------------- HELPERS ----------------
async def send_log(text):
    try:
        await app.send_message(LOG_CHANNEL, text)
    except Exception as e:
        print("Log error:", e)

def format_episode_buttons(episodes):
    buttons = []
    for ep in sorted(episodes):
        buttons.append([InlineKeyboardButton(f"Episode {ep}", callback_data=f"ep_{ep}")])
    return InlineKeyboardMarkup(buttons)

def format_quality_buttons(episode, series, qualities):
    buttons = []
    for q in qualities:
        buttons.append([InlineKeyboardButton(q, callback_data=f"q_{episode}_{series}_{q}")])
    return InlineKeyboardMarkup(buttons)

def format_caption(template, series, episode, quality):
    if not template:
        template = "🎬 {series} Episode {episode}\n📌 Quality: {quality}"
    return template.format(series=series.title(), episode=episode, quality=quality)

# ---------------- START ----------------
@app.on_message(filters.private & filters.command("start"))
async def start_bot(client, message):
    user = message.from_user
    users_col.update_one(
        {"user_id": user.id},
        {"$set": {"username": user.username, "start_time": datetime.utcnow()}},
        upsert=True
    )
    await message.reply(f"👋 Hi {user.first_name}, Welcome to Serial Bot!")
    await send_log(f"✅ Bot started by @{user.username} ({user.id})")

# ---------------- SEARCH ----------------
@app.on_message(filters.private & filters.text)
async def search_episode(client, message):
    query = message.text.lower().strip()

    search_msg = await message.reply("🔍 Searching...")
    await asyncio.sleep(1)
    await search_msg.delete()

    # Extract episode number from any format
    ep_match = re.search(r'\d+', query)
    if not ep_match:
        await message.reply("❌ Please enter episode number like 44 or S06E44")
        return

    ep_number = int(ep_match.group())
    series_name = "big boss marathi"

    episode = episodes_col.find_one({
        "series": series_name,
        "episode": ep_number
    })

    if not episode:
        await message.reply("❌ Episode not found.")
        await send_log(f"❌ User searched EP {ep_number} but not found")
        return

    await message.reply(
        "Select Episode 👇",
        reply_markup=format_episode_buttons([ep_number])
    )

# ---------------- EPISODE SELECT ----------------
@app.on_callback_query(filters.regex("^ep_"))
async def episode_select(client, callback_query):
    episode = int(callback_query.data.split("_")[1])
    await callback_query.message.delete()

    ep_data = episodes_col.find_one({
        "series": "big boss marathi",
        "episode": episode
    })

    if not ep_data:
        await callback_query.message.reply("❌ Episode data missing.")
        await send_log(f"❌ Episode {episode} missing in DB")
        return

    qualities = list(ep_data["qualities"].keys())

    await callback_query.message.reply(
        "Select Quality 👇",
        reply_markup=format_quality_buttons(
            episode,
            ep_data["series"],
            qualities
        )
    )

# ---------------- QUALITY SELECT ----------------
@app.on_callback_query(filters.regex("^q_"))
async def quality_select(client, callback_query):
    data = callback_query.data.split("_")
    episode = int(data[1])
    series = data[2]
    quality = data[3]

    await callback_query.message.delete()

    ep_data = episodes_col.find_one({
        "series": series,
        "episode": episode
    })

    if not ep_data:
        await callback_query.message.reply("❌ Episode not found in DB.")
        return

    file_id = ep_data["qualities"].get(quality)

    if not file_id:
        await callback_query.message.reply("❌ Quality not available.")
        return

    caption_template = ep_data.get("caption_template")
    caption = format_caption(caption_template, series, episode, quality)
    thumbnail = ep_data.get("thumbnail")

    await callback_query.message.reply_video(
        file_id,
        caption=caption,
        thumb=thumbnail,
        parse_mode="markdown"
    )

# ---------------- AUTO EPISODE STORE ----------------
@app.on_message(filters.channel & filters.video)
async def new_episode_monitor(client, message):
    if message.chat.id != SERIES_CHANNEL:
        return

    caption = message.caption.lower() if message.caption else ""

    ep_match = re.search(r's?\d*e?(\d+)', caption)
    if not ep_match:
        await send_log("⚠️ Episode format not detected in caption")
        return

    ep_number = int(ep_match.group(1))
    series_name = "big boss marathi"

    quality = next((q for q in ["480p","720p","1080p"] if q in caption), "480p")

    existing = episodes_col.find_one({
        "series": series_name,
        "episode": ep_number
    })

    if existing:
        episodes_col.update_one(
            {"series": series_name, "episode": ep_number},
            {"$set": {f"qualities.{quality}": message.video.file_id}}
        )
    else:
        episodes_col.insert_one({
            "series": series_name,
            "episode": ep_number,
            "qualities": {quality: message.video.file_id},
            "caption_template": None,
            "thumbnail": message.video.thumbs[0].file_id if message.video.thumbs else None,
            "added_on": datetime.utcnow()
        })

    await send_log(f"📥 Added EP {ep_number} {quality}")

# ---------------- RUN ----------------
if __name__ == "__main__":
    print("Bot running...")
    app.run()
