# backend/sheet_utils.py
import os
import json
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

# ----------------------
# Google Sheet URL
# ----------------------
SHEET_URL = "https://docs.google.com/spreadsheets/d/12UDiRnjQXwxcHFjR3SWdz8lB45-OTGHBzm3YVcExnsQ/edit"

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
        print("⚠️ GOOGLE_CREDENTIALS or GOOGLE_CREDENTIALS_JSON not set in environment")
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
    ws = get_sheet(sheet_name)
    if not ws:
        return pd.DataFrame()
    try:
        records = ws.get_all_records()
        return pd.DataFrame(records)
    except Exception as e:
        print(f"⚠️ Could not fetch data from {sheet_name}: {e}")
        return pd.DataFrame()

# ----------------------
# Listings History
# ----------------------
def get_listing_history_df():
    """
    Returns 'Listings History' as DataFrame.
    """
    ws = ensure_tab("Listings History", columns=["Email", "Date", "Car", "Price", "Tone", "Listing"])
    try:
        records = ws.get_all_records()
        return pd.DataFrame(records)
    except Exception as e:
        print(f"⚠️ Could not fetch Listings History: {e}")
        return pd.DataFrame()

def append_listing_history(email, date, car_text, price, tone, listing_snippet):
    """
    Append listing to 'Listings History'.
    """
    data = {
        "Email": email,
        "Date": date,
        "Car": car_text,
        "Price": price,
        "Tone": tone,
        "Listing": listing_snippet
    }
    return append_to_google_sheet("Listings History", data)

# ----------------------
# Social Media Data
# ----------------------
def get_social_media_data(sheet_name="Social_Media"):
    """
    Returns social media analytics DataFrame.
    Auto-creates sheet if missing.
    """
    ws = ensure_tab(sheet_name, columns=["Email", "Date", "Platform", "Make", "Model", "Reach", "Impressions", "Revenue", "Conversions", "Ad Cost"])
    df = pd.DataFrame()
    try:
        records = ws.get_all_records()
        df = pd.DataFrame(records)
    except Exception as e:
        print(f"⚠️ Could not fetch Social_Media records: {e}")

    # Fallback demo data
    if df.empty:
        df = pd.DataFrame([
            {"Make": "BMW", "Model": "X5", "Platform": "Instagram", "Reach": 4500, "Impressions": 12000, "Revenue": 52000, "Conversions": 12, "Ad Cost": 4000, "Date": pd.Timestamp.today()},
            {"Make": "BMW", "Model": "X5", "Platform": "Facebook", "Reach": 4000, "Impressions": 11000, "Revenue": 48000, "Conversions": 10, "Ad Cost": 3500, "Date": pd.Timestamp.today()},
            {"Make": "Audi", "Model": "A3", "Platform": "Instagram", "Reach": 3000, "Impressions": 9000, "Revenue": 35000, "Conversions": 8, "Ad Cost": 2800, "Date": pd.Timestamp.today()},
            {"Make": "Audi", "Model": "A3", "Platform": "Facebook", "Reach": 2500, "Impressions": 8000, "Revenue": 32000, "Conversions": 6, "Ad Cost": 2500, "Date": pd.Timestamp.today()},
            {"Make": "VW", "Model": "Golf", "Platform": "TikTok", "Reach": 5000, "Impressions": 13000, "Revenue": 56000, "Conversions": 15, "Ad Cost": 4200, "Date": pd.Timestamp.today()},
        ])

    # Convert types
    for col in ["Reach", "Impressions", "Revenue", "Conversions", "Ad Cost"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    else:
        df["Date"] = pd.Timestamp.today()

    return df

# ----------------------
# User Activity
# ----------------------
def get_user_activity_data():
    """
    Returns 'User_Activity' as DataFrame.
    Creates sheet if missing.
    """
    ws = ensure_tab("User_Activity", columns=["Email", "Start_Date", "Expiry_Date", "Status", "Usage_Count"])
    try:
        records = ws.get_all_records()
        df = pd.DataFrame(records)
    except Exception as e:
        print(f"⚠️ Could not fetch User_Activity: {e}")
        df = pd.DataFrame()

    if df.empty:
        df = pd.DataFrame(columns=["Email", "Start_Date", "Expiry_Date", "Status", "Usage_Count"])

    # Convert dates
    for col in ["Start_Date", "Expiry_Date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    if "Usage_Count" in df.columns:
        df["Usage_Count"] = pd.to_numeric(df["Usage_Count"], errors="coerce").fillna(0)

    return df
