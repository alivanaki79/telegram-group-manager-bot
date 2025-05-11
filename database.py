# database.py

import requests
from config import SUPABASE_URL, SUPABASE_API_KEY

headers = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json",
}

def add_group(group_id: int, title: str) -> bool:
    url = f"{SUPABASE_URL}/rest/v1/groups"
    data = {"id": group_id, "title": title}
    response = requests.post(url, headers=headers, json=data)
    return response.status_code in [200, 201]

def set_subscription(group_id: int, start_date: str, end_date: str) -> bool:
    url = f"{SUPABASE_URL}/rest/v1/subscriptions"
    data = {"group_id": group_id, "start_date": start_date, "end_date": end_date}
    response = requests.post(url, headers=headers, json=data)
    return response.status_code in [200, 201]

def get_subscription(group_id: int):
    url = f"{SUPABASE_URL}/rest/v1/subscriptions?group_id=eq.{group_id}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if data:
            return data[0]
    return None
