# backend/sheet_utils.py
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
def get_sheet():
    """
    Returns the main sheet object using service account JSON from environment.
    """
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not raw:
        print("⚠️ GOOGLE_CREDENTIALS_JSON not set in environment")
        return None

    try:
        info = json.loads(raw)
        creds = Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"]
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_url(SHEET_URL).sheet1
        return sheet
    except Exception as e:
        print(f"⚠️ Could not connect to Google Sheet: {e}")
        return None


# ----------------------
# Append a row to a Google Sheet
# ----------------------
def append_to_google_sheet(sheet_name, data_dict):
    """
    Appends a dictionary of data to a sheet. 
    sheet_name: Name of the sheet (e.g., "AI_Metrics")
    data_dict: dictionary with keys as columns
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
            # add header row
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
    Appends a summary of the listing to a 'Listings History' sheet.
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
# Get a sheet as a Pandas DataFrame
# ----------------------
def get_sheet_data(sheet_name):
    """
    Returns the data from a given sheet as a Pandas DataFrame.
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
# Get activity for a single user
# ----------------------
def get_user_activity_data(user_email):
    """
    Returns a DataFrame of a user's listings from the main sheet.
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

