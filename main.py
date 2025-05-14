import asyncio
import os
import uvicorn
import re
import requests
from datetime import timedelta, datetime, time, timezone
from zoneinfo import ZoneInfo
from pytz import timezone as pytz_timezone

from fastapi import FastAPI, Request
from telegram import Update, ChatPermissions, Bot
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, ChatMemberHandler, JobQueue
)

from config import BOT_TOKEN, SUPABASE_URL, SUPABASE_API_KEY
from database import add_group, get_subscription_status, add_warning, remove_warning, get_warning_count, update_lock_status, is_group_locked, get_night_lock_status, update_night_lock, update_last_night_lock_applied, update_last_night_lock_released

TEHRAN = pytz_timezone("Asia/Tehran")

headers = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json",
}

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
    application.add_handler(CommandHandler("ban", ban))
    application.add_handler(CommandHandler("unban", unban))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, link_filter))
    application.add_handler(CommandHandler("lock", lock))
    application.add_handler(CommandHandler("unlock", unlock))
    application.add_handler(CommandHandler("nightlockon", enable_night_lock))
    application.add_handler(CommandHandler("nightlockoff", disable_night_lock_temporarily))
    application.add_handler(CommandHandler("lockstatus", lock_status))
    
    # ست کردن وبهوک در تلگرام
    await application.bot.set_webhook(WEBHOOK_URL)
    await application.initialize()
    await application.start()

    # ✅ اجرای periodic_check بعد از مقداردهی application
    asyncio.create_task(periodic_check())
    
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
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    admin_ids = [admin.user.id for admin in chat_admins]

    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("❌ فقط ادمین‌ها می‌توانند اخطار بدهند.")
        return

    user = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    if not user:
        await update.message.reply_text("باید روی پیام فرد مورد نظر ریپلای کنید.")
        return

    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    issuer = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)

    if user.id == context.bot.id:
        await update.message.reply_text("❌ نمی‌توانید به ربات اخطار بدهید.")
        return

    if member.status in ['administrator', 'creator'] and issuer.status != 'creator':
        await update.message.reply_text("❌ فقط صاحب گروه می‌تواند روی ادمین‌ها اعمالی انجام دهد.")
        return

    count = add_warning(update.effective_chat.id, user.id, user.username or "بدون‌نام")
    await update.message.reply_text(
        f"⚠️ به کاربر {user.mention_html()} اخطار شماره {count} داده شد.",
        parse_mode='HTML'
    )

    if count >= 3:
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=datetime.utcnow() + timedelta(hours=1)
        )
        await update.message.reply_text(
            f"🚫 کاربر {user.mention_html()} به دلیل دریافت ۳ اخطار، به مدت ۱ ساعت ساکت شد.",
            parse_mode='HTML'
        )

# خوش آمد گویی
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for user in update.message.new_chat_members:
        tehran_tz = pytz.timezone('Asia/Tehran')
        now = datetime.now(tehran_tz).strftime("%Y/%m/%d ساعت %H:%M")

        group_title = update.effective_chat.title  # گرفتن اسم گروه

        text = (
            f"🌸 سلام {user.mention_html()} عزیز! 👋\n\n"
            f"به گپ {group_title} خوش اومدی! 🎉\n\n"
            f"🕒 تاریخ و زمان ورود: {now} 🌹"
        )

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode="HTML"
        )



# دستور ساکت شدن کاربر
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    admin_ids = [admin.user.id for admin in chat_admins]

    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("❌ فقط ادمین‌ها می‌توانند سکوت کنند.")
        return

    user = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    if not user:
        await update.message.reply_text("باید روی پیام فرد مورد نظر ریپلای کنی.")
        return

    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    issuer = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)

    if user.id == context.bot.id:
        await update.message.reply_text("❌ نمی‌توانید ربات را محدود کنید.")
        return

    if member.status in ['administrator', 'creator'] and issuer.status != 'creator':
        await update.message.reply_text("❌ فقط صاحب گروه می‌تواند روی ادمین‌ها اعمالی انجام دهد.")
        return

    duration = context.args[0] if context.args else "10m"
    match = re.match(r"(\d+)([smhd])", duration)
    if not match:
        await update.message.reply_text("فرمت زمان نامعتبر است. مثال: 10m یا 2h")
        return

    amount, unit = int(match.group(1)), match.group(2)
    delta = {"s": timedelta(seconds=amount), "m": timedelta(minutes=amount),
             "h": timedelta(hours=amount), "d": timedelta(days=amount)}[unit]
    until_date = datetime.utcnow() + delta

    await context.bot.restrict_chat_member(
        update.effective_chat.id,
        user.id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=until_date
    )
    await update.message.reply_text(f"🔇 کاربر {user.mention_html()} برای {duration} ساکت شد.", parse_mode='HTML')

# دستور حذف سکوت کاربر
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # فقط ادمین‌ها اجازه دارند
    chat_admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    admin_ids = [admin.user.id for admin in chat_admins]

    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("❌ فقط ادمین‌ها می‌توانند سکوت را بردارند.")
        return

    # باید روی پیام کاربر ریپلای زده شود
    user_to_unmute = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    if not user_to_unmute:
        await update.message.reply_text("لطفاً روی پیام کاربر ریپلای بزنید.")
        return

    await context.bot.restrict_chat_member(
        chat_id=update.effective_chat.id,
        user_id=user_to_unmute.id,
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
)
    )

    await update.message.reply_text(f"🔓 @{user_to_unmute.username or 'کاربر'} از حالت سکوت خارج شد.")


# حذف همه اخطارها
async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    admin_ids = [admin.user.id for admin in chat_admins]
    
    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("❌ فقط ادمین‌ها می‌توانند اخطار را حذف کنند.")
        return

    user = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    if not user:
        await update.message.reply_text("باید روی پیام شخص مورد نظر ریپلای کنی.")
        return

    count_to_remove = int(context.args[0]) if context.args and context.args[0].isdigit() else 1
    new_count = remove_warning(update.effective_chat.id, user.id, count_to_remove)
    await update.message.reply_text(f"ℹ️ اخطارهای @{user.username} کم شد. تعداد جدید: {new_count}")


# دستور بن کردن
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    admin_ids = [admin.user.id for admin in chat_admins]

    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("❌ فقط ادمین‌ها می‌توانند کاربران را بن کنند.")
        return

    user = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    if not user:
        await update.message.reply_text("باید روی پیام فرد مورد نظر ریپلای کنید.")
        return

    member = await context.bot.get_chat_member(update.effective_chat.id, user.id)
    issuer = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)

    if user.id == context.bot.id:
        await update.message.reply_text("❌ نمی‌توانید ربات را بن کنید.")
        return

    if member.status in ['administrator', 'creator'] and issuer.status != 'creator':
        await update.message.reply_text("❌ فقط صاحب گروه می‌تواند روی ادمین‌ها اعمالی انجام دهد.")
        return

    await context.bot.ban_chat_member(update.effective_chat.id, user.id)
    await update.message.reply_text(f"🚫 کاربر {user.mention_html()} از گروه بن شد.", parse_mode='HTML')


# دستور آن‌بن کردن
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    admin_ids = [admin.user.id for admin in chat_admins]
    
    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("❌ فقط ادمین‌ها می‌توانند از بن خارج کنند.")
        return

    user = update.message.reply_to_message.from_user if update.message.reply_to_message else None
    if not user:
        await update.message.reply_text("باید روی پیام کاربر ریپلای کنی.")
        return

    await context.bot.unban_chat_member(update.effective_chat.id, user.id)
    await update.message.reply_text(f"✅ @{user.username or 'کاربر'} از بن خارج شد.")


# حذف لینک
async def link_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    if "http://" in message.text or "https://" in message.text or "t.me" in message.text:
        sender = await context.bot.get_chat_member(update.effective_chat.id, message.from_user.id)
        if sender.status not in ['administrator', 'creator']:
            await message.delete()
            count = add_warning(update.effective_chat.id, message.from_user.id, message.from_user.username or "بدون‌نام")
            await message.reply_text(
                f"❌ ارسال لینک بدون هماهنگی با ادمین ممنوع است.\n⚠️ اخطار شماره {count} ثبت شد."
            )


# قفل گروه
async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    chat_admins = await context.bot.get_chat_administrators(chat_id)
    admin_ids = [admin.user.id for admin in chat_admins]

    if user_id not in admin_ids:
        await update.message.reply_text("❌ فقط ادمین‌ها می‌توانند گروه را قفل کنند.")
        return

    duration = context.args[0] if context.args else None
    until = None

    if duration:
        match = re.match(r"^(\d+)([mhd])$", duration)
        if match:
            value, unit = int(match.group(1)), match.group(2)
            if unit == 'm':
                until = datetime.utcnow() + timedelta(minutes=value)
            elif unit == 'h':
                until = datetime.utcnow() + timedelta(hours=value)
            elif unit == 'd':
                until = datetime.utcnow() + timedelta(days=value)
        else:
            await update.message.reply_text("❌ فرمت زمان اشتباه است. مثل 10m یا 2h یا 1d")
            return

    # اعمال محدودیت
    await context.bot.set_chat_permissions(
        chat_id=chat_id,
        permissions=ChatPermissions(can_send_messages=False)
    )

    # ذخیره در دیتابیس
    update_lock_status(chat_id, True, until.isoformat() if until else None)

    duration_text = ""
    if until:
        if unit == 'm':
            duration_text = f" برای {value} دقیقه"
        elif unit == 'h':
            duration_text = f" برای {value} ساعت"
        elif unit == 'd':
            duration_text = f" برای {value} روز"

    await update.message.reply_text(f"🔒 گروه قفل شد{duration_text}.")


async def check_and_unlock_expired_groups(bot: Bot):
    url = f"{SUPABASE_URL}/rest/v1/groups?select=group_id,lock_until,is_locked"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return

    for group in response.json():
        group_id = group["group_id"]
        is_locked = group["is_locked"]
        lock_until = group.get("lock_until")

        if is_locked and lock_until:
            lock_until_dt = datetime.fromisoformat(lock_until)
            if datetime.now(timezone.utc) > lock_until_dt:
                # باز کردن گروه
                await bot.set_chat_permissions(
                    chat_id=group_id,
                    permissions=ChatPermissions(
                        can_send_messages=True,
                        can_send_audios=True,
                        can_send_documents=True,
                        can_send_photos=True,
                        can_send_videos=True,
                        can_send_video_notes=True,
                        can_send_voice_notes=True,
                        can_send_polls=True,
                        can_send_other_messages=True,
                        can_add_web_page_previews=True
                    )
                )
                
                print(f"🔓 باز کردن خودکار گروه {group_id} چون زمانش تموم شده.")
                
                # پیام باز شدن خودکار
                try:
                    await bot.send_message(
                        chat_id=group_id,
                        text="🔓 قفل گروه به‌صورت خودکار باز شد."
                    )
                except:
                    pass  # اگر ربات بن شده بود یا نتونست پیام بده

                # بروزرسانی دیتابیس
                update_lock_status(group_id, False, None)

# ✅ سپس بلافاصله بعدش:
async def periodic_check():
    while True:
        print("🔁 در حال بررسی گروه‌های قفل‌شده...")
        await check_and_unlock_expired_groups(application.bot)
        await asyncio.sleep(60)


async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    admin_ids = [admin.user.id for admin in chat_admins]

    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("❌ فقط ادمین‌ها می‌توانند گروه را باز کنند.")
        return

    # باز کردن همه مجوزها برای ارسال پیام
    await context.bot.set_chat_permissions(
        chat_id=update.effective_chat.id,
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )
    )

    # به‌روزرسانی وضعیت قفل‌شدن
    update_lock_status(update.effective_chat.id, False, None)
    
    await update.message.reply_text("🔓 گروه باز شد.")

def update_lock_status(group_id: int, is_locked: bool, unlock_time: str = None):
    data = {
        "is_locked": is_locked,
        "unlock_time": unlock_time
    }
    url = f"{SUPABASE_URL}/rest/v1/groups?group_id=eq.{group_id}"
    requests.patch(url, headers=headers, json=data)

async def check_and_apply_night_lock(bot: Bot):
    now_utc = datetime.now(timezone.utc)
    now_tehran = now_utc.astimezone(TEHRAN)

    if not (2 <= now_tehran.hour < 7):
        return

    url = f"{SUPABASE_URL}/rest/v1/groups?select=group_id,night_lock_active,night_lock_disabled_until,is_locked,last_night_lock_applied"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print("❌ خطا در واکشی گروه‌ها")
        return

    for group in response.json():
        group_id = group["group_id"]
        active = group.get("night_lock_active", False)
        disabled_until = group.get("night_lock_disabled_until")
        is_locked = group.get("is_locked", False)
        last_applied = group.get("last_night_lock_applied")

        if not active or is_locked:
            continue

        if disabled_until:
            try:
                disabled_dt = datetime.fromisoformat(disabled_until)
                if now_utc < disabled_dt:
                    continue
            except:
                pass

        if last_applied:
            try:
                last_dt = datetime.fromisoformat(last_applied)
                if last_dt.date() == now_tehran.date():
                    continue  # دیشب اعمال شده
            except:
                pass

        try:
            await bot.set_chat_permissions(chat_id=group_id, permissions=ChatPermissions(can_send_messages=False))
            await bot.send_message(chat_id=group_id, text="🌙 قفل شبانه فعال شد.")
            update_lock_status(group_id, True)
            # ثبت تاریخ قفل
            url2 = f"{SUPABASE_URL}/rest/v1/groups?group_id=eq.{group_id}"
            requests.patch(url2, headers=headers, json={"last_night_lock_applied": now_utc.isoformat()})
        except Exception as e:
            print(f"❌ خطا در قفل گروه {group_id}: {e}")

async def check_and_release_night_lock(bot: Bot):
    now_utc = datetime.now(timezone.utc)
    now_tehran = now_utc.astimezone(TEHRAN)

    if now_tehran.hour != 7:
        return

    url = f"{SUPABASE_URL}/rest/v1/groups?select=group_id,is_locked,last_night_lock_released"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return

    for group in response.json():
        group_id = group["group_id"]
        is_locked = group.get("is_locked", False)
        last_released = group.get("last_night_lock_released")

        if not is_locked:
            continue

        if last_released:
            try:
                released_dt = datetime.fromisoformat(last_released)
                if released_dt.date() == now_tehran.date():
                    continue  # امروز باز شده قبلاً
            except:
                pass

        try:
            await bot.set_chat_permissions(
                chat_id=group_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_audios=True,
                    can_send_documents=True,
                    can_send_photos=True,
                    can_send_videos=True,
                    can_send_video_notes=True,
                    can_send_voice_notes=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True
                )
            )
            await bot.send_message(chat_id=group_id, text="🔓 قفل شبانه به پایان رسید.")
            update_lock_status(group_id, False)
            # ثبت زمان باز شدن
            url2 = f"{SUPABASE_URL}/rest/v1/groups?group_id=eq.{group_id}"
            requests.patch(url2, headers=headers, json={"last_night_lock_released": now_utc.isoformat()})
        except Exception as e:
            print(f"❌ خطا در باز کردن گروه {group_id}: {e}")

async def send_night_lock_warning(bot: Bot):
    now_utc = datetime.now(timezone.utc)
    now_tehran = now_utc.astimezone(TEHRAN)

    if now_tehran.hour != 1 or now_tehran.minute != 50:
        return

    url = f"{SUPABASE_URL}/rest/v1/groups?select=group_id,night_lock_active"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return

    for group in response.json():
        if group.get("night_lock_active", False):
            try:
                await bot.send_message(
                    chat_id=group["group_id"],
                    text="⏰ قفل شبانه تا ۱۰ دقیقه دیگر فعال می‌شود.\nبرای غیرفعال کردن امشب، ادمین‌ها می‌توانند بزنند:\n`/disable_nightlock`",
                    parse_mode="Markdown"
                )
            except:
                pass

async def disable_night_lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    admins = await context.bot.get_chat_administrators(chat_id)
    if user_id not in [admin.user.id for admin in admins]:
        return await update.message.reply_text("❌ فقط ادمین‌ها می‌توانند قفل شبانه را غیرفعال کنند.")

    until = datetime.now(timezone.utc) + timedelta(hours=6)
    url = f"{SUPABASE_URL}/rest/v1/groups?group_id=eq.{chat_id}"
    response = requests.patch(url, headers=headers, json={"night_lock_disabled_until": until.isoformat()})

    if response.status_code in [200, 204]:
        await update.message.reply_text("✅ قفل شبانه برای امشب غیرفعال شد.")
    else:
        await update.message.reply_text("❌ خطا در غیرفعال‌سازی قفل شبانه.")

async def periodic_check():
    while True:
        print("🔁 periodic check...")
        await check_and_unlock_expired_groups(application.bot)
        await send_night_lock_warning(application.bot)
        await check_and_apply_night_lock(application.bot)
        await check_and_release_night_lock(application.bot)
        await asyncio.sleep(60)
