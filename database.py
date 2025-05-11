import requests
from datetime import datetime, timedelta
from config import SUPABASE_URL, SUPABASE_API_KEY

headers = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json"
}

def add_group(group_id, title):
    now = datetime.utcnow().isoformat()

    # 1. ثبت در جدول groups
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/groups",
        headers=headers,
        json={"group_id": group_id, "title": title, "created_at": now}
    )

    if res.status_code not in [200, 201]:
        # اگر قبلاً ثبت شده، ادامه بده
        if "duplicate key" not in res.text:
            print("خطا در ثبت گروه:", res.text)
            return False

    # 2. ایجاد اشتراک 30 روزه
    start = datetime.utcnow().date().isoformat()
    end = (datetime.utcnow() + timedelta(days=30)).date().isoformat()

    requests.post(
        f"{SUPABASE_URL}/rest/v1/subscriptions",
        headers=headers,
        json={"group_id": group_id, "start_date": start, "end_date": end}
    )

    # 3. تنظیمات پیش‌فرض
    requests.post(
        f"{SUPABASE_URL}/rest/v1/settings",
        headers=headers,
        json={
            "group_id": group_id,
            "welcome_message": "خوش آمدی!",
            "filter_links": True,
            "filter_words": [],
            "silent_mode": False
        }
    )

    return True

def get_subscription_status(group_id):
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/subscriptions?group_id=eq.{group_id}",
        headers=headers
    )

    if res.status_code != 200 or not res.json():
        return None

    data = res.json()[0]
    end_date = datetime.fromisoformat(data["end_date"])
    remaining = (end_date - datetime.utcnow()).days

    return {
        "end_date": data["end_date"],
        "days_left": remaining
    }
