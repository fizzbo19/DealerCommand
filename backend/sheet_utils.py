# backend/sheet_utils.py
import os
import json
import requests
import pandas as pd
from datetime import datetime

# Set your Apps Script Web App URL in env or here:
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL") or "https://script.google.com/macros/s/AKfycbzI_ZIoU6sMFBJv7GnehZ6Fkj4EXMm2oceIO3vfdJRjlKrSr3T4fH1IY0A4-csNYypr/exec"
TIMEOUT = 15

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
# Basic DB functions (JSON storage)
# -----------------------
def save_record(record_type, email, data, record_id=None):
    """Append a new JSON record to the DealerCommand_DB sheet."""
    payload = {
        "action": "append",
        "record_type": record_type,
        "email": email,
        "data": data
    }
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
# Backwards-compat helpers for your frontend
# -----------------------
def append_to_google_sheet(sheet_name, data_dict):
    """
    Backwards compatible interface used by app.py.
    Instead of writing to many tabs, we write a JSON record with Record_Type = sheet_name.
    """
    try:
        # keep a copy of raw data in Data_JSON and also try to store top-level email if available
        email = data_dict.get("Email") or data_dict.get("email") or ""
        # convert everything to normal python types (avoid numpy types)
        clean_data = json.loads(json.dumps(data_dict, default=str))
        res = save_record(record_type=sheet_name, email=email, data=clean_data)
        return bool(res.get("success"))
    except Exception as e:
        print("append_to_google_sheet error:", e)
        return False

def get_sheet_data(sheet_name):
    """
    Returns a pandas DataFrame by fetching records with Record_Type == sheet_name and then
    flattening the Data_JSON for convenience.
    """
    try:
        raw = get_records(record_type=sheet_name)
        if not raw:
            return pd.DataFrame()
        rows = []
        for r in raw:
            # Data_JSON_parsed may already be present (Apps Script sets it), fallback to parsing
            try:
                parsed = r.get("Data_JSON_parsed") if "Data_JSON_parsed" in r else json.loads(r.get("Data_JSON","{}"))
            except Exception:
                parsed = {}
            # merge top-level props
            out = {"ID": r.get("ID"), "Email": r.get("Email"), "Record_Type": r.get("Record_Type"),
                   "Created_At": r.get("Created_At"), "Updated_At": r.get("Updated_At")}
            # parsed might be dict with nested values
            if isinstance(parsed, dict):
                for k,v in parsed.items():
                    out[k] = v
            else:
                out["Data"] = parsed
            rows.append(out)
        return pd.DataFrame(rows)
    except Exception as e:
        print("get_sheet_data error:", e)
        return pd.DataFrame()

# -----------------------
# Inventory helpers (for compatibility)
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

# -----------------------
# Utility: migrate old sheet rows -> DB
# -----------------------
def migrate_sheet_tab(tab_name, email_field=None):
    """
    Pulls old sheet by name (via Apps Script raw_sheet action) and appends each row to DB.
    Useful to migrate Inventory, Dealership_Profiles, Listings, etc.
    """
    try:
        # call doGet raw_sheet
        payload = {"sheet": tab_name, "action": "raw_sheet"}
        resp = call_script(payload, method="GET")
        if not resp.get("success"):
            return False, resp.get("error","unknown")
        rows = resp.get("data",[])
        for r in rows:
            email = r.get(email_field) if email_field else (r.get("Email") or "")
            save_record(record_type=tab_name, email=email, data=r)
        return True, f"Migrated {len(rows)} rows from {tab_name}"
    except Exception as e:
        return False, str(e)

# -------------------------------
# API helper functions
# -------------------------------

def api_save_inventory(email, item):
    try:
        resp = requests.post(f"{BACKEND_URL}/inventory", json={"email": email, "item": item})
        return resp.json().get("success", False)
    except Exception as e:
        st.error(f"⚠️ API error saving inventory: {e}")
        return False

def api_get_inventory(email):
    try:
        resp = requests.get(f"{BACKEND_URL}/inventory", params={"email": email})
        return resp.json().get("inventory", [])
    except Exception as e:
        st.error(f"⚠️ API error fetching inventory: {e}")
        return []

def api_save_dealership_profile(email, profile):
    try:
        resp = requests.post(f"{BACKEND_URL}/dealership/profile", json={"email": email, "profile": profile})
        return resp.json().get("success", False)
    except Exception as e:
        st.error(f"⚠️ API error saving profile: {e}")
        return False

def api_get_dealership_profile(email):
    try:
        resp = requests.get(f"{BACKEND_URL}/dealership/profile", params={"email": email})
        return resp.json().get("profile", {})
    except Exception as e:
        st.error(f"⚠️ API error fetching profile: {e}")
        return {}

def api_increment_platinum_usage(email, count=1):
    try:
        resp = requests.post(f"{BACKEND_URL}/platinum/usage", json={"email": email, "count": count})
        return resp.json().get("success", False)
    except Exception as e:
        st.error(f"⚠️ API error incrementing usage: {e}")
        return False

def api_save_custom_report(email, config):
    try:
        resp = requests.post(f"{BACKEND_URL}/custom/report", json={"email": email, "config": config})
        return resp.json().get("success", False), resp.json().get("message", "")
    except Exception as e:
        return False, str(e)

# -----------------------
# Small helper for debugging
# -----------------------
if __name__ == "__main__":
    print("sheet_utils loaded. APPS_SCRIPT_URL:", APPS_SCRIPT_URL)
