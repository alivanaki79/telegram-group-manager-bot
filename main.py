import os
import uvicorn
from telegram import ChatMember
from telegram.ext import MessageHandler, filters
from database import add_warning
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, ContextTypes
)
from config import BOT_TOKEN
from database import add_group, get_subscription_status

app = FastAPI()
application: Application = None  # برای مدیریت بات تلگرام

# آدرس وبهوک برای تلگرام
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}{WEBHOOK_PATH}"

# دستور /start برای ثبت گروه
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("این دستور فقط در گروه‌ها قابل استفاده است.")
        return

    group_id = update.effective_chat.id
    title = update.effective_chat.title or "بدون عنوان"

    if add_group(group_id, title):
        await update.message.reply_text(f"✅ گروه «{title}» با موفقیت ثبت شد.")

    days = get_subscription_status(group_id)
    if days == -1:
        await update.message.reply_text("❌ اشتراکی برای این گروه پیدا نشد.")
    elif days <= 3:
        await update.message.reply_text(f"⚠️ اشتراک این گروه تا {days} روز دیگر منقضی می‌شود.")
    else:
        await update.message.reply_text(f"📅 اشتراک این گروه تا {days} روز دیگر فعال است.")

# رویداد شروع برنامه
@app.on_event("startup")
async def startup():
    global application
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("warn", warn))

    # ست کردن وبهوک در تلگرام
    await application.bot.set_webhook(WEBHOOK_URL)
    await application.initialize()
    await application.start()
    print(f"✅ Webhook set to {WEBHOOK_URL}")

# هندل کردن پیام‌های دریافتی از تلگرام
@app.post(WEBHOOK_PATH)
async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"status": "ok"}

# برای تست در مرورگر
@app.get("/")
def root():
    return {"status": "Bot is running!"}

# اجرای برنامه با uvicorn
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)

# اخطار به کاربر
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # فقط ادمین‌ها اجازه دارند اخطار بدهند
    chat_admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    admin_ids = [admin.user.id for admin in chat_admins]
    
    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("❌ فقط ادمین‌ها می‌توانند اخطار بدهند.")
        return

    if not context.args:
        await update.message.reply_text("لطفاً یک یوزرنیم یا ریپلای مشخص کن.")
        return

    user_to_warn = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    if not user_to_warn:
        await update.message.reply_text("باید روی پیام شخص مورد نظر ریپلای کنی.")
        return

    count = add_warning(update.effective_chat.id, user_to_warn.id, user_to_warn.username or "بدون نام")

    if count >= 3:
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user_to_warn.id,
            permissions=ChatMember.NO_PERMISSIONS,
            until_date=None
        )
        await update.message.reply_text(f"🚫 @{user_to_warn.username} به دلیل دریافت 3 اخطار، ساکت شد.")
    else:
        await update.message.reply_text(f"⚠️ @{user_to_warn.username} یک اخطار گرفت. مجموع اخطارها: {count}")
