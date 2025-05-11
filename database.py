import requests
from datetime import datetime, timedelta
from config import SUPABASE_URL, SUPABASE_API_KEY

HEADERS = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json"
}

def add_group(group_id, title):
    # بررسی وجود گروه
    check = requests.get(
        f"{SUPABASE_URL}/rest/v1/groups?group_id=eq.{group_id}",
        headers=HEADERS
    )
    if check.status_code == 200 and check.json():
        return False  # گروه قبلاً ثبت شده

    now = datetime.utcnow()
    expires_at = now + timedelta(days=30)

    data = {
        "group_id": group_id,
        "title": title,
        "joined_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "warned": False
    }

    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/groups",
        headers=HEADERS,
        json=data
    )

    return res.status_code in [200, 201]

def get_all_groups():
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/groups",
        headers=HEADERS
    )
    if res.status_code == 200:
        return res.json()
    return []

def update_warned(group_id, warned=True):
    res = requests.patch(
        f"{SUPABASE_URL}/rest/v1/groups?group_id=eq.{group_id}",
        headers=HEADERS,
        json={"warned": warned}
    )
    return res.status_code == 204

def delete_expired_groups():
    now = datetime.utcnow().isoformat()
    res = requests.delete(
        f"{SUPABASE_URL}/rest/v1/groups?expires_at=lt.{now}",
        headers=HEADERS
    )
    return res.status_code == 204
