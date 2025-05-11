import os
import uvicorn
from telegram.ext import MessageHandler, filters
from database import add_warning
from database import remove_warning
from fastapi import FastAPI, Request
from telegram import Update
from telegram import ChatPermissions

permissions=ChatPermissions(
    can_send_messages=False,
    can_send_media_messages=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False
)


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
    application.add_handler(CommandHandler("mute", mute))
    application.add_handler(CommandHandler("unmute", unmute))
    application.add_handler(CommandHandler("unwarn", unwarn))


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

# مشخص کردن کاربر
async def get_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # اگر ریپلای کرده بود
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user

    # اگر آرگومان داده بود
    if context.args:
        user_input = context.args[0]

        # اگر آیدی عددی بود
        if user_input.isdigit():
            try:
                return await context.bot.get_chat_member(update.effective_chat.id, int(user_input)).user
            except:
                return None

        # اگر یوزرنیم بود
        if user_input.startswith('@'):
            try:
                return await context.bot.get_chat_member(update.effective_chat.id, user_input).user
            except:
                return None

    return None
    
# اخطار به کاربر
from database import add_warning  # اطمینان حاصل کن این بالای فایل هست

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    admin_ids = [admin.user.id for admin in chat_admins]

    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("❌ فقط ادمین‌ها می‌توانند اخطار بدهند.")
        return

    user_to_warn = await get_target_user(update, context)
    if not user_to_warn:
        await update.message.reply_text("❗ لطفاً آیدی یا یوزرنیم کاربر رو وارد کن یا روی پیامش ریپلای بزن.")
        return

    count = add_warning(update.effective_chat.id, user_to_warn.id, user_to_warn.username or "بدون نام")

    if count >= 3:
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user_to_warn.id,
            permissions=ChatMember.NO_PERMISSIONS,
            until_date=None
        )
        await update.message.reply_text(f"🚫 @{user_to_warn.username} به دلیل دریافت ۳ اخطار، ساکت شد.")
    else:
        await update.message.reply_text(f"⚠️ @{user_to_warn.username} یک اخطار گرفت. مجموع اخطارها: {count}")

# دستور ساکت شدن کاربر
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    admin_ids = [admin.user.id for admin in chat_admins]

    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("❌ فقط ادمین‌ها می‌توانند کاربر را ساکت کنند.")
        return

    user = await get_target_user(update, context)
    if not user:
        await update.message.reply_text("❗ لطفاً آیدی یا یوزرنیم کاربر رو وارد کن یا روی پیامش ریپلای بزن.")
        return

    await context.bot.restrict_chat_member(
        chat_id=update.effective_chat.id,
        user_id=user.id,
        permissions=ChatMember.NO_PERMISSIONS,
        until_date=None
    )
    await update.message.reply_text(f"🔇 @{user.username} ساکت شد.")

# دستور حذف سکوت کاربر
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    admin_ids = [admin.user.id for admin in chat_admins]

    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("❌ فقط ادمین‌ها می‌توانند سکوت را حذف کنند.")
        return

    user = await get_target_user(update, context)
    if not user:
        await update.message.reply_text("❗ لطفاً آیدی یا یوزرنیم کاربر رو وارد کن یا روی پیامش ریپلای بزن.")
        return

    await context.bot.restrict_chat_member(
        chat_id=update.effective_chat.id,
        user_id=user.id,
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )
    )
    await update.message.reply_text(f"🔊 @{user.username} می‌تونه دوباره پیام بده.")

from database import remove_warning

# حذف همه اخطارها
async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    admin_ids = [admin.user.id for admin in chat_admins]

    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("❌ فقط ادمین‌ها می‌توانند اخطار را حذف کنند.")
        return

    user = await get_target_user(update, context)
    if not user:
        await update.message.reply_text("❗ لطفاً آیدی یا یوزرنیم کاربر رو وارد کن یا روی پیامش ریپلای بزن.")
        return

    removed = remove_warning(update.effective_chat.id, user.id)
    if removed:
        await update.message.reply_text(f"✅ همه‌ی اخطارهای @{user.username} حذف شد.")
    else:
        await update.message.reply_text(f"ℹ️ هیچ اخطاری برای @{user.username} ثبت نشده.")
