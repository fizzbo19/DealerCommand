# backend/inventory_manager.py

from backend.sheet_utils import api_get, api_post, get_sheet_data, append_to_google_sheet
from backend.sheet_utils import get_dealership_profile, save_dealership_profile

INV_API = "inventory"

def save_inventory_item(data_dict):
    """
    Saves a listing to Google Sheets.
    """
    return append_to_google_sheet("Listings", data_dict)

def get_inventory_for_user(email):
    """
    Retrieves all inventory items for a specific user from the Listings sheet.
    """
    df = get_sheet_data("Listings")
    if df is None or df.empty:
        return []
    df.columns = [str(c).strip() for c in df.columns]
    email_col = next((c for c in df.columns if c.lower() == "email"), None)
    if not email_col:
        return []
    df[email_col] = df[email_col].astype(str).str.lower()
    return df[df[email_col] == email.lower()].to_dict(orient="records")

def delete_inventory_item(email, listing_id):
    """
    Deletes a listing by email and listing id.
    """
    return api_post(INV_API, {
        "action": "delete",
        "email": email,
        "id": listing_id
    })

# ---- Dealership profile helper ----
def login_user(email):
    if not email:
        return None
    return get_dealership_profile(email)

def save_profile(email, name, phone, location):
    profile = {"Name": name, "Phone": phone, "Location": location}
    return save_dealership_profile(email, profile)

def get_profile(email):
    return get_dealership_profile(email)

