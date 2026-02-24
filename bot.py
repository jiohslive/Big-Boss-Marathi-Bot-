import os
import asyncio
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient

# ---------------- ENV VARIABLES ----------------
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH"))
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URL = os.environ.get("MONGO_URL")
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL"))        # log channel
SERIES_CHANNEL = int(os.environ.get("SERIES_CHANNEL"))  # series upload channel

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
    except:
        pass

def format_episode_buttons(episodes, page=0, per_page=10):
    """Returns InlineKeyboardMarkup for a page of episodes"""
    start = page * per_page
    end = start + per_page
    buttons = []
    for ep in episodes[start:end]:
        buttons.append([InlineKeyboardButton(str(ep), callback_data=f"ep_{ep}_page{page}")])
    nav_buttons = []
    if start > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"nav_{page-1}"))
    if end < len(episodes):
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"nav_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    return InlineKeyboardMarkup(buttons)

def format_quality_buttons(episode, series, qualities):
    buttons = [[InlineKeyboardButton(q, callback_data=f"q_{episode}_{series}_{q}")] for q in qualities]
    return InlineKeyboardMarkup(buttons)

def format_caption(template, series, episode, quality, link=None):
    if not template:
        template = "🎬 {series} S{episode}\n📌 Quality: {quality}"
    return template.format(series=series.title(), episode=episode, quality=quality, link=link or "")

# ---------------- BOT START ----------------
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

# ---------------- SEARCH EPISODES ----------------
@app.on_message(filters.private & filters.text)
async def search_episode(client, message):
    query = message.text.lower().strip()
    search_msg = await message.reply("🔍 Searching...")
    await asyncio.sleep(1)
    await search_msg.delete()

    # Multi-series support
    if "s" in query and "e" in query:
        # Extract episode number
        try:
            ep_number = int("".join(filter(str.isdigit, query.split("e")[1].split()[0])))
        except:
            await message.reply("❌ Invalid format. Use S06E44")
            return
        series_name = query.split("s")[0].strip() or "big boss marathi"
        episode = episodes_col.find_one({"series": series_name, "episode": ep_number})
        if episode:
            await message.reply("Select Episode 👇", reply_markup=format_episode_buttons([ep_number]))
        else:
            await message.reply("❌ Episode not found.")
    else:
        await message.reply("❌ Invalid input. Include episode number e.g. S06E44")

# ---------------- EPISODE SELECTION ----------------
@app.on_callback_query(filters.regex("^ep_"))
async def episode_select(client, callback_query):
    data = callback_query.data.split("_")
    episode = int(data[1])
    page_info = data[2]  # optional page info
    await callback_query.message.delete()

    ep_data = episodes_col.find_one({"episode": episode})
    if not ep_data:
        await callback_query.message.reply("❌ Episode data missing.")
        return

    qualities = ep_data["qualities"].keys()
    await callback_query.message.reply(
        "Select Quality 👇",
        reply_markup=format_quality_buttons(episode, ep_data["series"], qualities)
    )

# ---------------- QUALITY SELECTION ----------------
@app.on_callback_query(filters.regex("^q_"))
async def quality_select(client, callback_query):
    data = callback_query.data.split("_")
    episode = int(data[1])
    series = data[2]
    quality = data[3]
    await callback_query.message.delete()

    ep_data = episodes_col.find_one({"series": series, "episode": episode})
    file_id = ep_data["qualities"][quality]
    caption_template = ep_data.get("caption_template")
    caption = format_caption(caption_template, series, episode, quality)
    thumbnail = ep_data.get("thumbnail")

    await callback_query.message.reply_video(
        file_id,
        caption=caption,
        thumb=thumbnail,
        parse_mode="markdown"
    )

# ---------------- AUTO EPISODE DETECTION ----------------
@app.on_message(filters.channel & filters.media)
async def new_episode_monitor(client, message):
    if message.chat.id != SERIES_CHANNEL:
        return

    caption = message.caption.lower() if message.caption else ""
    if "s" in caption and "e" in caption:
        try:
            ep_number = int("".join(filter(str.isdigit, caption.split("e")[1].split()[0])))
        except:
            return
        series_name = "big boss marathi"
        quality = next((q for q in ["480p","720p","1080p"] if q in caption), "unknown")

        existing = episodes_col.find_one({"series": series_name, "episode": ep_number})
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
                "caption_template": f"🎬 {series_name.title()} S{ep_number}\n📌 Quality: {quality}",
                "thumbnail": message.video.thumbs[0].file_id if message.video.thumbs else None,
                "added_on": datetime.utcnow()
            })

        await send_log(f"📥 New episode added: {series_name.title()} S{ep_number} {quality}")

# ---------------- ERROR HANDLER ----------------
@app.on_message(filters.private)
async def error_handler(client, message):
    try:
        pass
    except Exception as e:
        await send_log(f"❌ Error: {e}")

# ---------------- RUN ----------------
if __name__ == "__main__":
    print("Bot running...")
    app.run()
