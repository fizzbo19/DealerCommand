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
# CORE HELPER TO CALL APPS SCRIPT
# -----------------------
def call_script(payload, method="POST"):
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
# BACKWARDS COMPATIBILITY
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


def get_sheet_data(sheet_name):
    try:
        raw = get_records(record_type=sheet_name)
        if not raw:
            return pd.DataFrame()
        rows = []
        for r in raw:
            try:
                parsed = r.get("Data_JSON_parsed") if "Data_JSON_parsed" in r else json.loads(r.get("Data_JSON","{}"))
            except Exception:
                parsed = {}
            out = {"ID": r.get("ID"), "Email": r.get("Email"), "Record_Type": r.get("Record_Type"),
                   "Created_At": r.get("Created_At"), "Updated_At": r.get("Updated_At")}
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


def migrate_sheet_tab(tab_name, email_field=None):
    try:
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


# -----------------------
# LEGACY / BACKWARDS HELPERS
# -----------------------
def get_user_activity_data(email=None):
    return get_listing_history_df(email=email)


def upsert_to_sheet(sheet_name, key_col="Email", data_dict=None):
    """
    Generic upsert helper for a sheet.
    Updates row by key_col if exists, else appends.
    """
    df = get_sheet_data(sheet_name)
    key_val = data_dict.get(key_col)
    if df.empty or key_val not in df.get(key_col, []).values:
        return append_to_google_sheet(sheet_name, data_dict)
    else:
        # Find existing row and update
        row = df[df[key_col] == key_val].iloc[0]
        record_id = row.get("ID")
        return upsert_record(record_id, sheet_name, key_val, data_dict)


# -----------------------
# DEALERSHIP PROFILE HELPERS
# -----------------------
def get_dealership_profile(email):
    df = get_sheet_data("Dealership_Profiles")
    if df.empty:
        return {}
    row = df[df["Email"].astype(str).str.lower() == email.lower()]
    if row.empty:
        return {}
    return row.iloc[0].to_dict()


def save_dealership_profile(email, profile_dict):
    df = get_sheet_data("Dealership_Profiles")
    existing = df[df["Email"].astype(str).str.lower() == email.lower()] if not df.empty else pd.DataFrame()
    if existing.empty:
        return append_to_google_sheet("Dealership_Profiles", {"Email": email, **profile_dict})
    else:
        record_id = existing.iloc[0].get("ID")
        return upsert_record(record_id, "Dealership_Profiles", email, {"Email": email, **profile_dict})


def api_get_dealership_profile(email):
    """
    Returns dict with 'Remaining_Listings' or other profile info
    Placeholder API simulation for backward compatibility.
    """
    profile = get_dealership_profile(email)
    profile["Remaining_Listings"] = profile.get("Remaining_Listings", 15)
    return profile


# -----------------------
# SOCIAL / ANALYTICS PLACEHOLDERS
# -----------------------
def get_social_media_data(platform=None, email=None):
    """Placeholder for social media activity data."""
    return pd.DataFrame()


# -----------------------
# CUSTOM REPORT PLACEHOLDER
# -----------------------
def save_custom_report(email, config):
    """Placeholder to save report"""
    return True


def load_custom_reports(email):
    """Placeholder to load reports"""
    return []


def apply_report_filters(df, filters):
    """Placeholder to filter DataFrame"""
    return df

# --------------------------
# INVENTORY API HELPERS
# --------------------------

def api_get_inventory(email: str):
    """
    Returns all inventory rows for a dealership based on email.
    Assumes sheet 'Inventory' contains a column 'Email' linking items.
    """
    df = get_sheet_data("Inventory")
    if df.empty:
        return []

    df["Email_lower"] = df["Email"].astype(str).str.lower()
    data = df[df["Email_lower"] == email.lower()]

    # Convert dataframe rows to dicts
    return data.drop(columns=["Email_lower"], errors="ignore").to_dict(orient="records")


def api_upsert_inventory(email: str, item: dict):
    """
    Inserts or updates an inventory row. Must contain 'Listing_ID'.
    """
    if "Listing_ID" not in item:
        raise ValueError("Inventory item must include Listing_ID")

    upsert_to_sheet(
        "Inventory",
        key_col="Listing_ID",
        data_dict={**item, "Email": email}
    )
    return True


def api_delete_inventory(listing_id: str):
    """
    Deletes an inventory listing by setting a 'Deleted' flag.
    """
    upsert_to_sheet(
        "Inventory",
        key_col="Listing_ID",
        data_dict={"Listing_ID": listing_id, "Deleted": "YES"}
    )
    return True


# --------------------------
# SAVE INVENTORY (alias)
# --------------------------

def api_save_inventory(email: str, item: dict):
    """
    Compatibility wrapper for older code.
    Same as api_upsert_inventory().
    """
    return api_upsert_inventory(email, item)



# -----------------------
# DEBUG
# -----------------------
if __name__ == "__main__":
    print("sheet_utils loaded. APPS_SCRIPT_URL:", APPS_SCRIPT_URL)
