# backend/sheet_utils.py
import os
import json
import pandas as pd
import requests
from datetime import datetime

# ------------------------------------
# CONFIG: Your Google Apps Script URL
# ------------------------------------
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbwYoMeaOKzIV8lCUb0INJKaG6NUzCbVVwgj_ebm6xq-TgMMod5MgWxkVAIN_9Sm9qpz/exec"

# ------------------------------------
# CORE HELPER: Make Request to Web App
# ------------------------------------
def call_script(payload):
    """Send POST payload to Google Apps Script Web App."""
    try:
        response = requests.post(APPS_SCRIPT_URL, json=payload)
        if response.status_code == 200:
            return response.json()
        return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ------------------------------------
# TAB CREATION
# ------------------------------------
def ensure_tab(tab_name, columns=None):
    payload = {
        "action": "ensure_tab",
        "tab_name": tab_name,
        "columns": columns or []
    }
    return call_script(payload)

def get_or_create_tab(tab_name, columns=None):
    return ensure_tab(tab_name, columns)

# ------------------------------------
# APPEND DATA
# ------------------------------------
def append_to_google_sheet(sheet_name, data_dict):
    payload = {
        "action": "append",
        "sheet": sheet_name,
        "data": data_dict
    }
    return call_script(payload)

# ------------------------------------
# GET SHEET DATA
# ------------------------------------
def get_sheet_data(sheet_name):
    payload = {
        "action": "get",
        "sheet": sheet_name
    }
    result = call_script(payload)
    if not result.get("success"):
        return pd.DataFrame()
    return pd.DataFrame(result.get("data", []))

# ------------------------------------
# UPSERT (UPDATE OR INSERT)
# ------------------------------------
def upsert_to_sheet(sheet_name, key_col, data_dict):
    payload = {
        "action": "upsert",
        "sheet": sheet_name,
        "key_col": key_col,
        "data": data_dict
    }
    return call_script(payload)

# ------------------------------------
# USER ACTIVITY
# ------------------------------------
def get_user_activity_data():
    df = get_sheet_data("User_Activity")
    if df.empty:
        return pd.DataFrame(columns=["Email","Start_Date","Expiry_Date","Status","Usage_Count","Plan"])
    
    for col in ["Start_Date", "Expiry_Date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    
    if "Usage_Count" in df.columns:
        df["Usage_Count"] = pd.to_numeric(df["Usage_Count"], errors="coerce").fillna(0).astype(int)
    
    return df

# ------------------------------------
# DEALERSHIP PROFILES
# ------------------------------------
def save_dealership_profile(email, profile_dict):
    profile_dict["Email"] = email
    return upsert_to_sheet("Dealership_Profiles", key_col="Email", data_dict=profile_dict)

def get_dealership_profile(email):
    df = get_sheet_data("Dealership_Profiles")
    profile = {"Email": email, "Name": "", "Phone": "", "Location": "", "Plan": "Free Trial"}
    if df.empty:
        return profile

    df["Email_lower"] = df["Email"].astype(str).str.lower()
    row = df[df["Email_lower"] == email.lower()]
    if not row.empty:
        last = row.iloc[-1]
        profile["Name"] = last.get("Name", "")
        profile["Phone"] = last.get("Phone", "")
        profile["Location"] = last.get("Location", "")
        profile["Plan"] = last.get("Plan", "Free Trial")
    return profile

# ------------------------------------
# INVENTORY FUNCTIONS
# ------------------------------------
def save_inventory_item(data_dict, unique_id=None):
    if unique_id:
        data_dict["ID"] = unique_id
        return upsert_to_sheet("Inventory", key_col="ID", data_dict=data_dict)
    return append_to_google_sheet("Inventory", data_dict)

def get_inventory_for_user(email):
    df = get_sheet_data("Inventory")
    if df.empty:
        return df
    df["Email_lower"] = df["Email"].astype(str).str.lower()
    return df[df["Email_lower"] == email.lower()]

def get_inventory_for_cars(email, car_ids):
    df = get_inventory_for_user(email)
    if df.empty or not car_ids:
        return pd.DataFrame()
    return df.loc[df["ID"].isin(car_ids)]

# ------------------------------------
# LISTING HISTORY
# ------------------------------------
def get_listing_history_df(email):
    df = get_sheet_data("Inventory")
    if df.empty:
        return pd.DataFrame()
    df["Email"] = df["Email"].astype(str).str.lower()
    df = df[df["Email"] == email.lower()].copy()
    if "Timestamp" in df.columns:
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    return df

# ------------------------------------
# SOCIAL MEDIA DATA
# ------------------------------------
def get_social_media_data(email=None):
    df = get_sheet_data("Social_Media")
    if df.empty:
        return df
    if email:
        df["Email_lower"] = df["Email"].astype(str).str.lower()
        df = df[df["Email_lower"] == email.lower()]
    return df

def filter_social_media(df, platform=None):
    if df.empty:
        return df
    if platform:
        return df[df["Platform"].str.lower() == platform.lower()]
    return df
