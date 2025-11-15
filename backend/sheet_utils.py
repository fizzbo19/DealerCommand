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

SHEET_ID = os.environ.get("SHEET_ID") or "https://docs.google.com/spreadsheets/d/1XkZJkCzWzQVZQuN9dPWnPHfBz4DMFEwZYKwzBGsMKV0/edit"


# ----------------------
# Google Sheet Connection
# ----------------------
def get_google_credentials():
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
        return creds
    except Exception as e:
        print(f"⚠️ Failed to load Google credentials: {e}")
        return None


def get_sheet(tab_name=None):
    creds = get_google_credentials()
    if not creds:
        return None
    try:
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


def get_or_create_tab(tab_name, columns=None):
    ws = ensure_tab(tab_name, columns)
    if ws is None:
        raise RuntimeError(f"Cannot access or create tab: {tab_name}")
    return ws


# ----------------------
# Append / Upsert Data
# ----------------------
def append_to_google_sheet(sheet_name, data_dict):
    ws = get_or_create_tab(sheet_name, columns=list(data_dict.keys()))
    try:
        ws.append_row(list(data_dict.values()))
        return True
    except Exception as e:
        print(f"⚠️ Could not append to sheet {sheet_name}: {e}")
        return False


def upsert_to_sheet(sheet_name, key_col, data_dict):
    """
    Adds or updates a row based on key_col (like Email or ID)
    """
    ws = get_or_create_tab(sheet_name, columns=list(data_dict.keys()))
    df = get_sheet_data(sheet_name)
    df[key_col + "_lower"] = df[key_col].astype(str).str.lower()
    key_val_lower = str(data_dict[key_col]).lower()

    if key_val_lower in df[key_col + "_lower"].values:
        row_idx = df.index[df[key_col + "_lower"] == key_val_lower][0] + 2  # +2 for header
        for col, val in data_dict.items():
            if col in df.columns:
                try:
                    col_idx = df.columns.get_loc(col) + 1
                    ws.update_cell(row_idx, col_idx, val)
                except Exception as e:
                    print(f"⚠️ Could not update cell {col}: {e}")
    else:
        append_to_google_sheet(sheet_name, data_dict)


# ----------------------
# Get Sheet as DataFrame
# ----------------------
def get_sheet_data(sheet_name):
    try:
        ws = get_sheet(sheet_name)
        if not ws:
            return pd.DataFrame()
        records = ws.get_all_records()
        return pd.DataFrame(records)
    except Exception as e:
        print(f"⚠️ Could not fetch data from {sheet_name}: {e}")
        return pd.DataFrame()


def load_sheet_df(sheet_name, parse_dates=None, numeric_cols=None):
    df = get_sheet_data(sheet_name)
    if df.empty:
        return df
    if parse_dates:
        for col in parse_dates:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
    if numeric_cols:
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


# ----------------------
# Upload to Drive
# ----------------------
def upload_image_to_drive(file_obj, filename, folder_id=None):
    file_obj.seek(0)  # ensure pointer at start
    creds = get_google_credentials()
    if not creds:
        return None
    try:
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
        service.permissions().create(fileId=file_id, body={"role": "reader", "type": "anyone"}).execute()
        return f"https://drive.google.com/uc?id={file_id}"
    except Exception as e:
        print(f"⚠️ Failed to upload image: {e}")
        return None


# ----------------------
# User / Dealership Helpers
# ----------------------
def get_user_activity_data():
    ws = get_or_create_tab("User_Activity", columns=["Email", "Start_Date", "Expiry_Date", "Status", "Usage_Count"])
    try:
        records = ws.get_all_records()
        df = pd.DataFrame(records)
    except Exception as e:
        print(f"⚠️ Could not fetch User_Activity: {e}")
        df = pd.DataFrame(columns=["Email","Start_Date","Expiry_Date","Status","Usage_Count"])

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
    from backend.trial_manager import TRIAL_DAYS, MAX_FREE_LISTINGS
    df = get_user_activity_data()
    email_lower = email.lower()
    df["Email_lower"] = df["Email"].astype(str).str.lower()
    matches = df[df["Email_lower"]==email_lower]

    if matches.empty:
        trial_status = "new"
        trial_expiry = pd.Timestamp.utcnow() + pd.Timedelta(days=TRIAL_DAYS)
        usage_count = 0
    else:
        last_row = matches.iloc[-1]
        trial_expiry = pd.to_datetime(last_row.get("Expiry_Date", pd.Timestamp.utcnow() + pd.Timedelta(days=TRIAL_DAYS)))
        usage_count = int(last_row.get("Usage_Count",0))
        trial_status = "active" if pd.Timestamp.utcnow() <= trial_expiry else "expired"

    plan = "Free Trial"
    remaining_listings = max(MAX_FREE_LISTINGS - usage_count,0)

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


def get_inventory_for_cars(email, car_ids):
    df = get_inventory_for_user(email)
    if df.empty or not car_ids:
        return pd.DataFrame()
    return df.loc[df.index.isin(car_ids), ["Make","Model","Year","Mileage","Fuel","Price","Features"]]


# ----------------------
# Listing History & Social Media
# ----------------------
def get_listing_history_df(email):
    df = get_sheet_data("Inventory")
    if df.empty:
        return pd.DataFrame()
    df["Email"] = df["Email"].astype(str).str.lower()
    user_df = df[df["Email"]==email.lower()].copy()
    if "Timestamp" in user_df.columns:
        user_df["Timestamp"] = pd.to_datetime(user_df["Timestamp"], errors="coerce")
    return user_df


def get_social_media_data(email):
    try:
        return pd.DataFrame({
            "Email": [email]*3,
            "Platform": ["TikTok","Instagram","YouTube"],
            "Views": [1200,900,500],
            "Likes": [87,65,41],
            "Clicks": [12,8,3],
            "Revenue": [500,700,300]
        })
    except:
        return pd.DataFrame()


def filter_social_media(df, platform=None):
    if df.empty:
        return df
    if platform:
        return df[df["Platform"].str.lower()==platform.lower()]
    return df

