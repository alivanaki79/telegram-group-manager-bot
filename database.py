import requests
from datetime import datetime, date, timedelta
from config import SUPABASE_URL, SUPABASE_API_KEY

headers = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json"
}

def add_group(group_id, title):
    url = f"{SUPABASE_URL}/rest/v1/groups"
    check_url = f"{url}?group_id=eq.{group_id}"
    res = requests.get(check_url, headers=headers)

    if res.status_code == 200 and res.json():
        return False  # گروه قبلاً ثبت شده

    data = {
        "group_id": group_id,
        "title": title
    }
    insert = requests.post(url, headers={**headers, "Content-Type": "application/json"}, json=data)

    if insert.status_code in [200, 201]:
        return add_subscription(group_id)
    return False

def add_subscription(group_id):
    url = f"{SUPABASE_URL}/rest/v1/subscriptions"
    today = date.today()
    end = today + timedelta(days=30)

    data = {
        "group_id": group_id,
        "start_date": today.isoformat(),
        "end_date": end.isoformat()
    }

    res = requests.post(url, headers={**headers, "Content-Type": "application/json"}, json=data)
    return res.status_code in [200, 201]

def get_subscription_status(group_id):
    url = f"{SUPABASE_URL}/rest/v1/subscriptions?group_id=eq.{group_id}&select=end_date"
    res = requests.get(url, headers=headers)
    data = res.json()

    if not data:
        return -1  # اشتراک یافت نشد

    end_date = datetime.fromisoformat(data[0]['end_date']).date()
    days_left = (end_date - date.today()).days
    return days_left

def add_warning(group_id: int, user_id: int, username: str):
    url = f"{SUPABASE_URL}/rest/v1/warnings"

    # بررسی وجود اخطار قبلی
    check_url = f"{url}?group_id=eq.{group_id}&user_id=eq.{user_id}"
    response = requests.get(check_url, headers=headers)
    data = response.json()

    if data:
        current_count = data[0]["count"] + 1
        update_data = {
            "count": current_count,
            "last_warning": datetime.utcnow().isoformat()
        }
        requests.patch(check_url, headers=headers, json=update_data)
        return current_count
    else:
        insert_data = [{
            "group_id": group_id,
            "user_id": user_id,
            "username": username,
            "count": 1,
            "last_warning": datetime.utcnow().isoformat()
        }]
        requests.post(url, headers=headers, json=insert_data)
        return 1
