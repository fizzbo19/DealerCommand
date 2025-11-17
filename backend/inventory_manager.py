# backend/inventory_manager.py

from backend.sheet_utils import api_get, api_post
from backend.sheet_utils import get_dealership_profile, save_dealership_profile

INV_API = "inventory"

def save_inventory_item(data_dict):
    return api_post(INV_API, {
        "action": "save",
        "data": data_dict
    })

def get_inventory_for_user(email):
    res = api_get(f"{INV_API}?email={email}")
    return res.get("inventory", []) if res else []

def delete_inventory_item(email, listing_id):
    return api_post(INV_API, {
        "action": "delete",
        "email": email,
        "id": listing_id
    })



def login_user(email):
    if not email:
        return None
    profile = get_dealership_profile(email)
    return profile

def save_profile(email, name, phone, location):
    profile = {"Name": name, "Phone": phone, "Location": location}
    return save_dealership_profile(email, profile)

def get_profile(email):
    return get_dealership_profile(email)
