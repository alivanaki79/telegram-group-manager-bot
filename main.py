# main.py

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext import Defaults
from database import add_group
from config import BOT_TOKEN
import os

from telegram.ext import ApplicationBuilder
from telegram.ext.webhook import WebhookServer

app = FastAPI()
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}{WEBHOOK_PATH}"

telegram_app: Application = None  # Global instance

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "group":
        await update.message.reply_text("این دستور فقط در گروه‌ها قابل استفاده است.")
        return

    group_id = update.effective_chat.id
    title = update.effective_chat.title or "بدون عنوان"

    if add_group(group_id, title):
        await update.message.reply_text(f"✅ گروه ثبت شد: {title}")
    else:
        await update.message.reply_text("❌ مشکلی در ثبت گروه پیش آمد.")

@app.on_event("startup")
async def on_startup():
    global telegram_app

    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))

    # راه‌اندازی webhook
    await telegram_app.bot.set_webhook(url=WEBHOOK_URL)
    await telegram_app.initialize()
    await telegram_app.start()
    print(f"Webhook set at {WEBHOOK_URL}")

@app.post(WEBHOOK_PATH)
async def handle_webhook(request: Request):
    json_data = await request.json()
    update = Update.de_json(json_data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}
