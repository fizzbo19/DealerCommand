# backend/sheet_utils.py
import os
import json
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
from datetime import datetime

# ----------------------
# Google Sheet URL
# ----------------------
SHEET_URL = os.environ.get("SHEET_URL") or "https://docs.google.com/spreadsheets/d/12UDiRnjQXwxcHFjR3SWdz8lB45-OTGHBzm3YVcExnsQ/edit"

# ----------------------
# Connect to Google Sheet
# ----------------------
def get_sheet(tab_name=None):
    """
    Returns the sheet object (optionally specify a tab name).
    Works with GOOGLE_CREDENTIALS or GOOGLE_CREDENTIALS_JSON.
    """
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON") or os.environ.get("GOOGLE_CREDENTIALS")
    if not raw:
        print("⚠️ GOOGLE_CREDENTIALS or GOOGLE_CREDENTIALS_JSON not set")
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
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_url(SHEET_URL)
        if tab_name:
            return spreadsheet.worksheet(tab_name)
        return spreadsheet.sheet1
    except Exception as e:
        print(f"⚠️ Could not connect to Google Sheet: {e}")
        return None

# ----------------------
# Ensure Tab Exists
# ----------------------
def ensure_tab(tab_name, columns=None):
    """
    Ensures a worksheet exists. Creates it with columns if missing.
    Returns the worksheet object.
    """
    sheet = get_sheet()
    if not sheet:
        return None
    ss = sheet.spreadsheet
    try:
        ws = ss.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = ss.add_worksheet(title=tab_name, rows=2000, cols=20)
        if columns:
            ws.append_row(columns)
        print(f"✅ Created new '{tab_name}' tab with columns: {columns}")
    return ws

# ----------------------
# Append to Sheet
# ----------------------
def append_to_google_sheet(sheet_name, data_dict):
    """
    Appends a dictionary to a sheet. Creates sheet if missing.
    Returns True on success, False on failure.
    """
    ws = ensure_tab(sheet_name, columns=list(data_dict.keys()))
    if not ws:
        return False
    try:
        ws.append_row(list(data_dict.values()))
        return True
    except Exception as e:
        print(f"⚠️ Could not append to sheet {sheet_name}: {e}")
        return False

# ----------------------
# Fetch Sheet Data as DataFrame
# ----------------------
def get_sheet_data(sheet_name):
    """
    Returns the given worksheet as a Pandas DataFrame.
    """
    try:
        ws = get_sheet(sheet_name)
        if not ws:
            return pd.DataFrame()
        records = ws.get_all_records()
        return pd.DataFrame(records)
    except Exception as e:
        print(f"⚠️ Could not fetch data from {sheet_name}: {e}")
        return pd.DataFrame()

# ----------------------
# Upload file to Google Drive
# ----------------------
def upload_image_to_drive(file_obj, filename, folder_id=None):
    """
    Uploads a file-like object to Google Drive and returns the shareable link.
    folder_id: optional Google Drive folder ID
    """
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON") or os.environ.get("GOOGLE_CREDENTIALS")
    if not raw:
        print("⚠️ GOOGLE_CREDENTIALS or GOOGLE_CREDENTIALS_JSON not set")
        return None

    try:
        info = json.loads(raw)
        creds = Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        service = build('drive', 'v3', credentials=creds)

        media = MediaIoBaseUpload(io.BytesIO(file_obj.read()), mimetype="image/png")
        file_metadata = {"name": filename}
        if folder_id:
            file_metadata["parents"] = [folder_id]

        uploaded = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        ).execute()

        file_id = uploaded.get("id")

        # Make file shareable
        service.permissions().create(
            fileId=file_id,
            body={"role": "reader", "type": "anyone"}
        ).execute()

        return f"https://drive.google.com/uc?id={file_id}"
    except Exception as e:
        print(f"⚠️ Failed to upload image: {e}")
        return None

# ----------------------
# User Activity Helpers
# ----------------------
def get_user_activity_data():
    """
    Returns 'User_Activity' as DataFrame.
    """
    ws = ensure_tab("User_Activity", columns=["Email", "Start_Date", "Expiry_Date", "Status", "Usage_Count"])
    try:
        records = ws.get_all_records()
        df = pd.DataFrame(records)
    except Exception as e:
        print(f"⚠️ Could not fetch User_Activity: {e}")
        df = pd.DataFrame(columns=["Email", "Start_Date", "Expiry_Date", "Status", "Usage_Count"])

    # Convert types
    for col in ["Start_Date", "Expiry_Date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    if "Usage_Count" in df.columns:
        df["Usage_Count"] = pd.to_numeric(df["Usage_Count"], errors="coerce").fillna(0).astype(int)
    return df

# ----------------------
# Dealership Profile Helpers
# ----------------------
def save_dealership_profile(email, profile_dict):
    """
    Saves or updates a dealership profile in 'Dealership_Profiles'.
    """
    ws = ensure_tab("Dealership_Profiles", columns=list(profile_dict.keys()))
    df = get_sheet_data("Dealership_Profiles")
    df["Email_lower"] = df["Email"].astype(str).str.lower()
    email_lower = email.lower()

    if email_lower in df["Email_lower"].values:
        row_idx = df.index[df["Email_lower"] == email_lower][0] + 2
        for col, val in profile_dict.items():
            try:
                col_idx = df.columns.get_loc(col) + 1
                ws.update_cell(row_idx, col_idx, val)
            except Exception as e:
                print(f"⚠️ Could not update cell {col}: {e}")
    else:
        profile_dict["Email"] = email
        append_to_google_sheet("Dealership_Profiles", profile_dict)
    return True

def get_dealership_profile(email):
    """
    Returns full dealership profile, including trial info and remaining listings.
    """
    from backend.trial_manager import get_user_activity_data, TRIAL_DAYS, MAX_FREE_LISTINGS

    df = get_user_activity_data()
    email_lower = email.lower()
    df["Email_lower"] = df["Email"].astype(str).str.lower()
    matches = df[df["Email_lower"] == email_lower]

    if matches.empty:
        trial_status = "new"
        trial_expiry = pd.Timestamp.utcnow() + pd.Timedelta(days=TRIAL_DAYS)
        usage_count = 0
    else:
        last_row = matches.iloc[-1]
        trial_expiry = pd.to_datetime(last_row.get("Expiry_Date", pd.Timestamp.utcnow() + pd.Timedelta(days=TRIAL_DAYS)))
        usage_count = int(last_row.get("Usage_Count", 0))
        trial_status = "active" if pd.Timestamp.utcnow() <= trial_expiry else "expired"

    plan = "Free Trial"
    remaining_listings = max(MAX_FREE_LISTINGS - usage_count, 0)

    return {
        "Email": email,
        "Trial_Status": trial_status,
        "Trial_Expiry": trial_expiry.to_pydatetime(),
        "Usage_Count": usage_count,
        "Plan": plan,
        "Remaining_Listings": remaining_listings
    }

# ----------------------
# Inventory Helpers
# ----------------------
def save_inventory_item(data_dict):
    """
    Append a car listing to 'Inventory'.
    """
    required_cols = ["Email", "Timestamp", "Make", "Model", "Year", "Mileage",
                     "Color", "Fuel", "Transmission", "Price", "Features", "Notes", "Status"]
    for col in required_cols:
        if col not in data_dict:
            data_dict[col] = ""
    return append_to_google_sheet("Inventory", data_dict)

def get_inventory_for_user(email):
    df = get_sheet_data("Inventory")
    if df.empty:
        return df
    df["Email_lower"] = df["Email"].astype(str).str.lower()
    return df[df["Email_lower"] == email.lower()]


