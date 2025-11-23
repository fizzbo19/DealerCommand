# backend/sheet_utils.py
import os
import json
import requests
import pandas as pd
from datetime import datetime
import streamlit as st

# Set your Apps Script Web App URL in env or here:
APPS_SCRIPT_URL = os.environ.get(
    "APPS_SCRIPT_URL"
) or "https://script.google.com/macros/s/AKfycbzI_ZIoU6sMFBJv7GnehZ6Fkj4EXMm2oceIO3vfdJRjlKrSr3T4fH1IY0A4-csNYypr/exec"
TIMEOUT = 15

# -----------------------
# CORE SCRIPT CALL
# -----------------------
def call_script(payload, method="POST"):
    """Call the Apps Script web app (POST preferred)."""
    try:
        if method.upper() == "GET":
            resp = requests.get(APPS_SCRIPT_URL, params=payload, timeout=TIMEOUT)
        else:
            resp = requests.post(APPS_SCRIPT_URL, json=payload, timeout=TIMEOUT)
        if resp.status_code != 200:
            return {"success": False, "error": f"HTTP {resp.status_code} - {resp.text}"}
        return resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

# -----------------------
# BASIC DB FUNCTIONS
# -----------------------
def save_record(record_type, email, data, record_id=None):
    payload = {"action": "append", "record_type": record_type, "email": email, "data": data}
    if record_id:
        payload["id"] = record_id
    res = call_script(payload)
    return res if isinstance(res, dict) else {"success": False, "error": "Invalid response"}

def upsert_record(record_id, record_type, email, data):
    payload = {"action": "upsert", "id": record_id, "record_type": record_type, "email": email, "data": data}
    return call_script(payload)

def get_records(record_type=None, email=None, limit=None, since=None):
    payload = {"action": "get_records"}
    if record_type: payload["record_type"] = record_type
    if email: payload["email"] = email
    if limit: payload["limit"] = limit
    if since: payload["since"] = since
    res = call_script(payload)
    if not res.get("success"):
        return []
    return res.get("data", [])

def query_records(filters=None, record_type=None, email=None, limit=None):
    payload = {"action": "query"}
    if filters: payload["filters"] = filters
    if record_type: payload["record_type"] = record_type
    if email: payload["email"] = email
    if limit: payload["limit"] = limit
    return call_script(payload)

# -----------------------
# BACKWARDS-COMPAT HELPERS
# -----------------------
def append_to_google_sheet(sheet_name, data_dict):
    try:
        email = data_dict.get("Email") or data_dict.get("email") or ""
        clean_data = json.loads(json.dumps(data_dict, default=str))
        res = save_record(record_type=sheet_name, email=email, data=clean_data)
        return bool(res.get("success"))
    except Exception as e:
        print("append_to_google_sheet error:", e)
        return False

def upsert_to_sheet(sheet_name, key_col="Email", data_dict=None):
    """Add or update a record in a sheet by key_col"""
    if data_dict is None:
        return False
    key_value = data_dict.get(key_col)
    if not key_value:
        return False
    # Check for existing record
    df = get_sheet_data(sheet_name)
    existing = df[df[key_col].astype(str).str.lower() == str(key_value).lower()]
    record_id = existing.iloc[0]["ID"] if not existing.empty else None
    return bool(
        upsert_record(record_id, sheet_name, key_value, data_dict).get("success", False)
    )

def get_sheet_data(sheet_name):
    try:
        raw = get_records(record_type=sheet_name)
        if not raw:
            return pd.DataFrame()
        rows = []
        for r in raw:
            parsed = r.get("Data_JSON_parsed") if "Data_JSON_parsed" in r else json.loads(r.get("Data_JSON", "{}"))
            out = {
                "ID": r.get("ID"),
                "Email": r.get("Email"),
                "Record_Type": r.get("Record_Type"),
                "Created_At": r.get("Created_At"),
                "Updated_At": r.get("Updated_At")
            }
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    out[k] = v
            else:
                out["Data"] = parsed
            rows.append(out)
        return pd.DataFrame(rows)
    except Exception as e:
        print("get_sheet_data error:", e)
        return pd.DataFrame()

# -----------------------
# INVENTORY & LISTINGS
# -----------------------
def get_inventory_for_user(email):
    df = get_sheet_data("Inventory")
    if df.empty:
        return pd.DataFrame()
    df["Email"] = df["Email"].astype(str)
    return df[df["Email"].str.lower() == str(email).lower()].copy()

def get_listing_history_df(email=None):
    df = get_sheet_data("Listings")
    if df.empty:
        return pd.DataFrame()
    if email:
        df = df[df["Email"].astype(str).str.lower() == email.lower()]
    return df

def get_user_activity_data(email=None):
    return get_listing_history_df(email=email)

# -----------------------
# DEALERSHIP PROFILE WRAPPERS
# -----------------------
def save_dealership_profile(email, profile):
    """Save dealership profile using existing API helper"""
    return api_save_dealership_profile(email, profile)

def get_dealership_profile(email):
    """Fetch dealership profile using existing API helper"""
    return api_get_dealership_profile(email)

# -----------------------
# API HELPERS
# -----------------------
def api_save_inventory(email, item):
    try:
        resp = requests.post(f"{os.environ.get('BACKEND_URL')}/inventory", json={"email": email, "item": item})
        return resp.json().get("success", False)
    except Exception as e:
        st.error(f"⚠️ API error saving inventory: {e}")
        return False

def api_get_inventory(email):
    try:
        resp = requests.get(f"{os.environ.get('BACKEND_URL')}/inventory", params={"email": email})
        return resp.json().get("inventory", [])
    except Exception as e:
        st.error(f"⚠️ API error fetching inventory: {e}")
        return []

def api_save_dealership_profile(email, profile):
    try:
        resp = requests.post(f"{os.environ.get('BACKEND_URL')}/dealership/profile", json={"email": email, "profile": profile})
        return resp.json().get("success", False)
    except Exception as e:
        st.error(f"⚠️ API error saving profile: {e}")
        return False

def api_get_dealership_profile(email):
    try:
        resp = requests.get(f"{os.environ.get('BACKEND_URL')}/dealership/profile", params={"email": email})
        return resp.json().get("profile", {})
    except Exception as e:
        st.error(f"⚠️ API error fetching profile: {e}")
        return {}

# -----------------------
# DEBUG
# -----------------------
if __name__ == "__main__":
    print("sheet_utils loaded. APPS_SCRIPT_URL:", APPS_SCRIPT_URL)

