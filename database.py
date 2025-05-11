# database.py

import requests
from config import SUPABASE_URL, SUPABASE_API_KEY

headers = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json"
}

def add_group(group_id, title):
    url = f"{SUPABASE_URL}/rest/v1/groups"
    data = {
        "group_id": group_id,
        "title": title
    }
    response = requests.post(url, json=data, headers=headers)
    return response.status_code == 201 or "duplicate" in response.text

