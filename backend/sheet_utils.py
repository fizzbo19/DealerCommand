import os
import json
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

# Google Sheet URL
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
# Ensure Social_Media Tab Exists
# ----------------------
def ensure_social_media_tab():
    """
    Checks if 'Social_Media' tab exists; creates it if missing with correct columns.
    """
    try:
        sheet = get_sheet()
        if not sheet:
            return None
        ss = sheet.spreadsheet
        try:
            return ss.worksheet("Social_Media")
        except gspread.exceptions.WorksheetNotFound:
            ws = ss.add_worksheet(title="Social_Media", rows=1000, cols=10)
            ws.append_row(["Email", "Date", "Platform", "Make", "Model", "Reach", "Impressions", "Revenue", "Conversions", "Ad Cost"])
            print("✅ Created new 'Social_Media' tab with correct columns.")
            return ws
    except Exception as e:
        print(f"⚠️ Could not ensure Social_Media tab: {e}")
        return None


# ----------------------
# Append a row to a Google Sheet
# ----------------------
def append_to_google_sheet(sheet_name, data_dict):
    """
    Appends a dictionary of data to a sheet.
    """
    sheet = get_sheet()
    if not sheet:
        return False

    try:
        ss = sheet.spreadsheet
        try:
            ws = ss.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            ws = ss.add_worksheet(title=sheet_name, rows=2000, cols=20)
            ws.append_row(list(data_dict.keys()))
        ws.append_row(list(data_dict.values()))
        return True
    except Exception as e:
        print(f"⚠️ Could not append to sheet {sheet_name}: {e}")
        return False


# ----------------------
# Append to listing history
# ----------------------
def append_listing_history(email, date, car_text, price, tone, listing_snippet):
    """
    Append user listing info to 'Listings History'.
    """
    sheet = get_sheet()
    if not sheet:
        return False
    try:
        ss = sheet.spreadsheet
        try:
            history_ws = ss.worksheet("Listings History")
        except gspread.exceptions.WorksheetNotFound:
            history_ws = ss.add_worksheet(title="Listings History", rows=2000, cols=6)
            history_ws.append_row(["Email", "Date", "Car", "Price", "Tone", "Listing"])
        history_ws.append_row([email, date, car_text, price, tone, listing_snippet])
        return True
    except Exception as e:
        print(f"⚠️ Could not append to Listings History: {e}")
        return False


# ----------------------
# Fetch sheet data as DataFrame
# ----------------------
def get_sheet_data(sheet_name):
    """
    Returns the given worksheet as a Pandas DataFrame.
    """
    sheet = get_sheet()
    if not sheet:
        return pd.DataFrame()
    try:
        ss = sheet.spreadsheet
        try:
            ws = ss.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            return pd.DataFrame()
        records = ws.get_all_records()
        return pd.DataFrame(records)
    except Exception as e:
        print(f"⚠️ Could not fetch data from {sheet_name}: {e}")
        return pd.DataFrame()


# ----------------------
# Listing history DataFrame
# ----------------------
def get_listing_history_df():
    """
    Fetch 'Listings History' as a DataFrame.
    """
    sheet = get_sheet()
    if not sheet:
        return pd.DataFrame()
    try:
        ss = sheet.spreadsheet
        history_ws = ss.worksheet("Listings History")
        records = history_ws.get_all_records()
        return pd.DataFrame(records)
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame()


# ----------------------
# User activity DataFrame
# ----------------------
def get_user_activity_data(user_email):
    """
    Return activity for a given user from AI_Metrics sheet.
    """
    try:
        df = get_sheet_data("AI_Metrics")
        if df.empty:
            return df
        if "Email" in df.columns:
            df = df[df["Email"].str.lower() == user_email.lower()]
        if "Timestamp" not in df.columns:
            df["Timestamp"] = pd.Timestamp.now()
        return df
    except Exception as e:
        print(f"⚠️ Error fetching user activity: {e}")
        return pd.DataFrame()


# ----------------------
# Social Media Data
# ----------------------
def get_social_media_data(sheet_name="Social_Media"):
    """
    Fetch social media analytics from Google Sheet or fallback to demo data.
    Columns expected: Email, Date, Platform, Make, Model, Reach, Impressions, Revenue, Conversions, Ad Cost
    """
    ws = ensure_social_media_tab()
    df = pd.DataFrame()

    if ws:
        try:
            records = ws.get_all_records()
            df = pd.DataFrame(records)
        except Exception as e:
            print(f"⚠️ Could not fetch Social_Media records: {e}")

    # If still empty, fallback demo
    if df.empty:
        df = pd.DataFrame([
            {"Make": "BMW", "Model": "X5", "Platform": "Instagram", "Reach": 4500, "Impressions": 12000, "Revenue": 52000, "Conversions": 12, "Ad Cost": 4000, "Date": pd.Timestamp.today()},
            {"Make": "BMW", "Model": "X5", "Platform": "Facebook", "Reach": 4000, "Impressions": 11000, "Revenue": 48000, "Conversions": 10, "Ad Cost": 3500, "Date": pd.Timestamp.today()},
            {"Make": "Audi", "Model": "A3", "Platform": "Instagram", "Reach": 3000, "Impressions": 9000, "Revenue": 35000, "Conversions": 8, "Ad Cost": 2800, "Date": pd.Timestamp.today()},
            {"Make": "Audi", "Model": "A3", "Platform": "Facebook", "Reach": 2500, "Impressions": 8000, "Revenue": 32000, "Conversions": 6, "Ad Cost": 2500, "Date": pd.Timestamp.today()},
            {"Make": "VW", "Model": "Golf", "Platform": "TikTok", "Reach": 5000, "Impressions": 13000, "Revenue": 56000, "Conversions": 15, "Ad Cost": 4200, "Date": pd.Timestamp.today()},
        ])

    # Convert columns to correct data types
    for col in ["Reach", "Impressions", "Revenue", "Conversions", "Ad Cost"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Ensure Date column
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    else:
        df["Date"] = pd.Timestamp.today()

    return df


# ----------------------
# Social Media Filtering
# ----------------------
def filter_social_media(df, make=None, model=None, min_price=None, max_price=None, fuel=None):
    """
    Filter social media DataFrame based on dealer query.
    """
    filtered = df.copy()
    if make:
        filtered = filtered[filtered["Make"].str.lower() == make.lower()]
    if model:
        filtered = filtered[filtered["Model"].str.lower() == model.lower()]
    if min_price is not None:
        filtered = filtered[filtered["Revenue"] >= min_price]
    if max_price is not None:
        filtered = filtered[filtered["Revenue"] <= max_price]
    if fuel and "Fuel" in df.columns:
        filtered = filtered[df["Fuel"].str.lower() == fuel.lower()]
    return filtered
