from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(i) for i in os.getenv("ADMIN_IDS", "").split(",") if i.isdigit()]
WEBHOOK_URL = os.getenv("WEBHOOK_URL")          # например https://mybot.onrender.com/webhook
HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", 8443))
