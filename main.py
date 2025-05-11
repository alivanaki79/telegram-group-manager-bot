# main.py

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv
from config import BOT_TOKEN
from database import add_group
import os

load_dotenv()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "group":
        await update.message.reply_text("این دستور فقط داخل گروه‌ها کار می‌کنه.")
        return

    group_id = update.effective_chat.id
    title = update.effective_chat.title or "بدون عنوان"

    if add_group(group_id, title):
        await update.message.reply_text(f"✅ گروه ثبت شد: {title}")
    else:
        await update.message.reply_text("❌ مشکلی در ثبت گروه پیش اومد.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("🤖 ربات آماده است...")
    app.run_polling()

