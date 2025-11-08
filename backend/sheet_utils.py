# backend/sheet_utils.py
import os
import json
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
# Append a new car listing
# ----------------------
def append_to_google_sheet(email, data_dict):
    """
    Appends a single car listing to the main sheet.
    Returns True if successful, False otherwise.
    """
    sheet = get_sheet()
    if not sheet:
        return False
    try:
        row = [
            email,
            data_dict.get("Make"),
            data_dict.get("Model"),
            data_dict.get("Year"),
            data_dict.get("Mileage"),
            data_dict.get("Color"),
            data_dict.get("Fuel Type"),
            data_dict.get("Transmission"),
            data_dict.get("Price"),
            data_dict.get("Features"),
            data_dict.get("Dealer Notes"),
        ]
        sheet.append_row(row)
        return True
    except Exception as e:
        print(f"⚠️ Could not append to main sheet: {e}")
        return False

# ----------------------
# Append to listing history
# ----------------------
def append_listing_history(email, date, car_text, price, tone, listing_snippet):
    """
    Appends a summary of the listing to a 'Listings History' sheet.
    Returns True if successful, False otherwise.
    """
    sheet = get_sheet()
    if not sheet:
        return False
    try:
        ss = sheet.spreadsheet
        try:
            history_ws = ss.worksheet("Listings History")
        except gspread.exceptions.WorksheetNotFound:
            history_ws = ss.add_worksheet(
                title="Listings History", rows=2000, cols=6
            )
            history_ws.append_row(["Email", "Date", "Car", "Price", "Tone", "Listing"])

        history_ws.append_row([email, date, car_text, price, tone, listing_snippet])
        return True
    except Exception as e:
        print(f"⚠️ Could not append to history: {e}")
        return False
    
    import pandas as pd

def get_user_activity_data(user_email):
    """Pull listing activity from Google Sheets for analytics."""
    try:
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("gcp_credentials.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(os.environ.get("GOOGLE_SHEET_ID")).sheet1
        records = sheet.get_all_records()

        df = pd.DataFrame(records)
        if "Email" in df.columns:
            df = df[df["Email"] == user_email]
        if "Timestamp" not in df.columns:
            df["Timestamp"] = pd.Timestamp.now()
        return df
    except Exception as e:
        print("Error fetching sheet data:", e)
        return pd.DataFrame()

