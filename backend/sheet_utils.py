# backend/sheet_utils.py
import os
import json
import pandas as pd
import gspread
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
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_url(SHEET_URL).sheet1
        return sheet
    except Exception as e:
        print(f"⚠️ Could not connect to Google Sheet: {e}")
        return None

# ----------------------
# Append a new record to the sheet
# ----------------------
def append_to_google_sheet(email, data_dict):
    """
    Appends a row of data to the main sheet.
    Returns True if successful, False otherwise.
    """
    sheet = get_sheet()
    if not sheet:
        return False
    try:
        row = [
            data_dict.get("Email", email),
            data_dict.get("Make", ""),
            data_dict.get("Model Name", ""),
            data_dict.get("Year", ""),
            data_dict.get("Mileage", ""),
            data_dict.get("Color", ""),
            data_dict.get("Fuel Type", ""),
            data_dict.get("Transmission", ""),
            data_dict.get("Price", ""),
            data_dict.get("Features", ""),
            data_dict.get("Dealer Notes", ""),
            data_dict.get("Listings Generated", 0),
            data_dict.get("Avg Response Time (s)", 0),
            data_dict.get("Avg Prompt Length", 0),
            data_dict.get("Status", "Pending Verification"),
            data_dict.get("Timestamp", pd.Timestamp.now().isoformat())
        ]
        sheet.append_row(row)
        return True
    except Exception as e:
        print(f"⚠️ Could not append to main sheet: {e}")
        return False

# ----------------------
# Fetch leaderboard / user activity data
# ----------------------
def get_user_activity_data(user_email=None):
    """
    Fetches all leaderboard metrics from Google Sheet.
    If user_email is provided, filters to that user as well.
    Returns a pandas DataFrame.
    """
    sheet = get_sheet()
    if not sheet:
        return pd.DataFrame()

    try:
        records = sheet.get_all_records()
        df = pd.DataFrame(records)

        # Ensure all necessary columns exist
        for col in ["Email", "Listings Generated", "Avg Response Time (s)", "Avg Prompt Length", "Status", "Timestamp"]:
            if col not in df.columns:
                df[col] = 0 if "Avg" in col or "Listings" in col else ""

        # Convert numeric columns
        df["Listings Generated"] = pd.to_numeric(df["Listings Generated"], errors="coerce").fillna(0)
        df["Avg Response Time (s)"] = pd.to_numeric(df["Avg Response Time (s)"], errors="coerce").fillna(0)
        df["Avg Prompt Length"] = pd.to_numeric(df["Avg Prompt Length"], errors="coerce").fillna(0)

        # Parse Timestamp
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")

        if user_email:
            df = df[df["Email"] == user_email]

        return df

    except Exception as e:
        print(f"⚠️ Error fetching sheet data: {e}")
        return pd.DataFrame()

