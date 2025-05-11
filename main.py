# main.py

import os
import uvicorn
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, ContextTypes
)
from config import BOT_TOKEN
from database import add_group

app = FastAPI()
application: Application = None  # Global variable for Telegram Application

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}{WEBHOOK_PATH}"

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
async def startup():
    global application
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    # Set webhook to this server
    await application.bot.set_webhook(WEBHOOK_URL)
    await application.initialize()
    await application.start()
    print(f"✅ Webhook set to {WEBHOOK_URL}")

@app.post(WEBHOOK_PATH)
async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"status": "ok"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))  # PORT متغیر مخصوص Render هست
    uvicorn.run("main:app", host="0.0.0.0", port=port)

