import os
import uvicorn
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, ContextTypes
)
from config import BOT_TOKEN
from database import add_group, get_all_groups, update_warned, delete_expired_groups
from datetime import datetime, timedelta
import asyncio

app = FastAPI()
application: Application = None

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}{WEBHOOK_PATH}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("این دستور فقط در گروه‌ها قابل استفاده است.")
        return

    group_id = update.effective_chat.id
    title = update.effective_chat.title or "بدون عنوان"

    if add_group(group_id, title):
        await update.message.reply_text(f"✅ گروه ثبت شد: {title}")
    else:
        await update.message.reply_text("❌ این گروه قبلاً ثبت شده یا خطایی رخ داده.")

async def check_subscriptions():
    while True:
        now = datetime.utcnow()
        groups = get_all_groups()

        for group in groups:
            gid = group["group_id"]
            expires = datetime.fromisoformat(group["expires_at"])
            warned = group.get("warned", False)

            if expires < now:
                await application.bot.send_message(chat_id=gid, text="❌ اشتراک گروه شما به پایان رسیده و ربات غیرفعال شد.")
                print(f"⛔ گروه حذف شد: {gid}")
            elif not warned and expires - now < timedelta(days=3):
                await application.bot.send_message(chat_id=gid, text="⏰ اشتراک شما کمتر از ۳ روز دیگر به پایان می‌رسد.")
                update_warned(gid)

        delete_expired_groups()
        await asyncio.sleep(3600 * 6)  # هر ۶ ساعت

@app.on_event("startup")
async def startup():
    global application
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    await application.bot.set_webhook(WEBHOOK_URL)
    await application.initialize()
    await application.start()
    asyncio.create_task(check_subscriptions())
    print(f"✅ Webhook set to {WEBHOOK_URL}")

@app.post(WEBHOOK_PATH)
async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"status": "ok"}

@app.get("/")
def root():
    return {"status": "Bot is alive!"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
