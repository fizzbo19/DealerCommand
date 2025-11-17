# backend/sheet_utils.py
import os
import json
import pandas as pd
import requests
from datetime import datetime
import gspread


# ------------------------------------
# CONFIG: Your Google Apps Script URL
# ------------------------------------
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbwYoMeaOKzIV8lCUb0INJKaG6NUzCbVVwgj_ebm6xq-TgMMod5MgWxkVAIN_9Sm9qpz/exec"


# ------------------------------------
# Core Helper: Make Request to Web App
# ------------------------------------
def call_script(payload):
    """Sends POST payload to Google Apps Script Web App."""
    try:
        response = requests.post(APPS_SCRIPT_URL, json=payload)
        if response.status_code == 200:
            return response.json()
        return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ------------------------------------
# Tab Creation
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
# Append Data
# ------------------------------------
def append_to_google_sheet(sheet_name, data_dict):
    payload = {
        "action": "append",
        "sheet": sheet_name,
        "data": data_dict
    }
    return call_script(payload)


# ------------------------------------
# Get Sheet Data
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
# UPSERT (Update or Insert)
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
        return pd.DataFrame(columns=[
            "Email", "Start_Date", "Expiry_Date", "Status", "Usage_Count", "Plan"
        ])

    for col in ["Start_Date", "Expiry_Date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    if "Usage_Count" in df.columns:
        df["Usage_Count"] = pd.to_numeric(df["Usage_Count"], errors="coerce").fillna(0).astype(int)

    return df


def save_dealership_profile(email, profile_dict):
    profile_dict["Email"] = email
    return upsert_to_sheet(
        "Dealership_Profiles",
        key_col="Email",
        data_dict=profile_dict
    )


def get_dealership_profile(email):
    df = get_sheet_data("Dealership_Profiles")

    profile = {
        "Email": email,
        "Name": "",
        "Phone": "",
        "Location": "",
        "Plan": "Free Trial"
    }

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
# Inventory Functions
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
    return df.loc[df["ID"].isin(car_ids), :]


# ------------------------------------
# Listing History & Social Media
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


def get_social_media_data(email):
    return get_sheet_data("Social_Media")


def filter_social_media(df, platform=None):
    if df.empty:
        return df
    if platform:
        return df[df["Platform"].str.lower() == platform.lower()]
    return df

def get_google_credentials():
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON") or os.environ.get("GOOGLE_CREDENTIALS")
    if not raw:
        return None
    try:
        info = json.loads(raw)
        creds = Credentials.from_service_account_info(
            info,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
        )
        return creds
    except Exception:
        return None

def get_sheet(tab_name=None):
    creds = get_google_credentials()
    if not creds:
        return None
    try:
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)
        if tab_name:
            return spreadsheet.worksheet(tab_name)
        return spreadsheet.sheet1
    except Exception:
        return None

def ensure_tab(tab_name, columns=None, max_retries=3):
    sheet = get_sheet()
    if not sheet:
        return None
    ss = sheet.spreadsheet
    attempt = 0
    while attempt < max_retries:
        try:
            ws = ss.worksheet(tab_name)
            return ws
        except gspread.exceptions.WorksheetNotFound:
            try:
                ws = ss.add_worksheet(title=tab_name, rows=2000, cols=max(20, len(columns or [])))
                if columns:
                    ws.append_row(columns)
                return ws
            except Exception:
                pass
        except Exception:
            pass
        attempt += 1
    class DummyWorksheet:
        def append_row(self, *args, **kwargs): pass
        def update_cell(self, *args, **kwargs): pass
        def get_all_records(self): return []
    return DummyWorksheet()

def get_or_create_tab(tab_name, columns=None):
    ws = ensure_tab(tab_name, columns)
    if ws:
        return ws
    class DummyWorksheet:
        def append_row(self, *args, **kwargs): pass
        def update_cell(self, *args, **kwargs): pass
        def get_all_records(self): return []
    return DummyWorksheet()

def append_to_google_sheet(sheet_name, data_dict):
    ws = get_or_create_tab(sheet_name, columns=list(data_dict.keys()))
    try:
        ws.append_row(list(data_dict.values()))
        return True
    except Exception:
        return False

def get_sheet_data(sheet_name):
    try:
        ws = get_sheet(sheet_name)
        if not ws:
            return pd.DataFrame()
        records = ws.get_all_records()
        return pd.DataFrame(records)
    except Exception:
        return pd.DataFrame()

def upsert_to_sheet(sheet_name, key_col, data_dict):
    df = get_sheet_data(sheet_name)
    ws = get_or_create_tab(sheet_name, columns=list(data_dict.keys()))
    if key_col not in data_dict:
        return append_to_google_sheet(sheet_name, data_dict)
    key_val = str(data_dict[key_col])
    if df.empty or key_col not in df.columns:
        return append_to_google_sheet(sheet_name, data_dict)
    df[key_col + "_lower"] = df[key_col].astype(str).str.lower()
    key_val_lower = str(key_val).lower()
    if key_val_lower in df[key_col + "_lower"].values:
        row_idx = df.index[df[key_col + "_lower"] == key_val_lower][0] + 2
        df_cols = df.columns.tolist()
        for col, val in data_dict.items():
            if col in df_cols:
                try:
                    col_idx = df_cols.index(col) + 1
                    ws.update_cell(row_idx, col_idx, val)
                except Exception:
                    pass
    else:
        return append_to_google_sheet(sheet_name, data_dict)
    return True

def get_user_activity_data():
    ws = get_or_create_tab("User_Activity", columns=["Email", "Start_Date", "Expiry_Date", "Status", "Usage_Count", "Plan"])
    try:
        records = ws.get_all_records()
        df = pd.DataFrame(records)
    except Exception:
        df = pd.DataFrame(columns=["Email","Start_Date","Expiry_Date","Status","Usage_Count", "Plan"])
    for col in ["Start_Date","Expiry_Date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    if "Usage_Count" in df.columns:
        df["Usage_Count"] = pd.to_numeric(df["Usage_Count"], errors="coerce").fillna(0).astype(int)
    return df

def save_dealership_profile(email, profile_dict):
    profile_dict["Email"] = email
    upsert_to_sheet("Dealership_Profiles", key_col="Email", data_dict=profile_dict)
    return True

def get_dealership_profile(email):
    df = get_sheet_data("Dealership_Profiles")
    profile = {"Email": email, "Name": "", "Phone": "", "Location": "", "Plan": "Free Trial"}
    if not df.empty and "Email" in df.columns:
        df["Email_lower"] = df["Email"].astype(str).str.lower()
        matches = df[df["Email_lower"] == email.lower()]
        if not matches.empty:
            last_row = matches.iloc[-1]
            profile["Name"] = last_row.get("Name", "")
            profile["Phone"] = last_row.get("Phone", "")
            profile["Location"] = last_row.get("Location", "")
            profile["Plan"] = last_row.get("Plan", "Free Trial")
    return profile

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
    return df[df["Email_lower"]==email.lower()]