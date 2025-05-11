import requests
from datetime import datetime, timedelta
from config import SUPABASE_URL, SUPABASE_API_KEY

HEADERS = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json"
}

def add_group(group_id: int, title: str) -> bool:
    # بررسی اینکه آیا گروه قبلاً ثبت شده
    response = requests.get(f"{SUPABASE_URL}/groups?group_id=eq.{group_id}", headers=HEADERS)
    if response.json():
        return False

    # ثبت در جدول groups
    group_data = {
        "group_id": group_id,
        "title": title
    }
    res = requests.post(f"{SUPABASE_URL}/groups", headers=HEADERS, json=group_data)

    # تنظیم پیام خوش‌آمدگویی پیش‌فرض و سایر تنظیمات
    settings_data = {
        "group_id": group_id,
        "welcome_message": "خوش آمدی!",
        "filter_links": True,
        "filter_words": [],
        "silent_mode": False
    }
    requests.post(f"{SUPABASE_URL}/settings", headers=HEADERS, json=settings_data)

    # ثبت اشتراک ۳۰ روزه
    today = datetime.utcnow().date()
    subscription_data = {
        "group_id": group_id,
        "start_date": str(today),
        "end_date": str(today + timedelta(days=30))
    }
    requests.post(f"{SUPABASE_URL}/subscriptions", headers=HEADERS, json=subscription_data)

    return res.status_code == 201

def get_subscription_status(group_id: int):
    response = requests.get(
        f"{SUPABASE_URL}/subscriptions?group_id=eq.{group_id}",
        headers=HEADERS
    )
    data = response.json()

    if not isinstance(data, list) or len(data) == 0:
        return "not_found"

    end_date_str = data[0].get('end_date')
    if not end_date_str:
        return "not_found"

    end_date = datetime.fromisoformat(end_date_str)
    remaining_days = (end_date - datetime.utcnow()).days
    return remaining_days

