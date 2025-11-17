# backend/auth_manager.py

from backend.sheet_utils import api_get, api_post

AUTH_API = "auth"

def login_user(email):
    if not email:
        return None
    res = api_post(AUTH_API, {"action": "login", "email": email})
    if not res or res.get("status") != "success":
        return None
    return res

def save_profile(email, name, phone, location):
    return api_post(AUTH_API, {
        "action": "save_profile",
        "email": email,
        "name": name,
        "phone": phone,
        "location": location
    })

def get_profile(email):
    return api_get(f"{AUTH_API}?email={email}")
