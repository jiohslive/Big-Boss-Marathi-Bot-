import os
from dotenv import load_dotenv

load_dotenv()

try:
    API_ID = int(os.environ["API_ID"])
    API_HASH = os.environ["API_HASH"]
    BOT_TOKEN = os.environ["BOT_TOKEN"]

    MONGO_URI = os.environ["MONGO_URI"]
    DB_NAME = os.environ["DB_NAME"]

    PRIVATE_CHANNEL_ID = int(os.environ["PRIVATE_CHANNEL_ID"])

    print("✅ ENV LOADED SUCCESSFULLY")

except Exception as e:
    print("❌ ENV ERROR:", e)
    raise e
