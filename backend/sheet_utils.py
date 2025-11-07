# backend/sheet_utils.py
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.sheet_utils import append_to_google_sheet


import gspread
from google.oauth2.service_account import Credentials

SHEET_URL = "https://docs.google.com/spreadsheets/d/12UDiRnjQXwxcHFjR3SWdz8lB45-OTGHBzm3YVcExnsQ/edit"

# Connect to Google Sheet
def get_sheet():
    try:
        creds = Credentials.from_service_account_file("service_account.json", scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ])
        client = gspread.authorize(creds)
        sheet = client.open_by_url(SHEET_URL).sheet1
        return sheet
    except Exception as e:
        print(f"Error accessing Google Sheet: {e}")
        return None


# Save car listing to sheet
def append_to_google_sheet(email, data_dict):
    sheet = get_sheet()
    if not sheet:
        return False
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


# Optional: logging listings in separate history tab
def append_listing_history(email, date, make, model, price, listing_preview):
    sheet = get_sheet()
    if not sheet:
        return False
    ss = sheet.spreadsheet
    try:
        history = ss.worksheet("Listings History")
    except gspread.exceptions.WorksheetNotFound:
        history = ss.add_worksheet(title="Listings History", rows="1000", cols="6")
        history.append_row(["Email", "Date", "Make", "Model", "Price", "Listing Preview"])

    history.append_row([email, date, make, model, price, listing_preview])
    return True



def append_listing_history(email, date, make, model, price, snippet):
    try:
        sheet = get_sheet()
        if not sheet:
            return
        ss = sheet.spreadsheet
        try:
            history_ws = ss.worksheet("Listings History")
        except gspread.exceptions.WorksheetNotFound:
            history_ws = ss.add_worksheet("Listings History", rows=1000, cols=10)

        history_ws.append_row([email, date, make, model, price, snippet])
    except Exception as e:
        print("⚠️ Could not append to history:", e)

def get_sheet():
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not raw:
        return None
    try:
        info = json.loads(raw)
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        client = gspread.authorize(creds)
        sheet = client.open_by_url(SHEET_URL).sheet1
        return sheet
    except Exception as e:
        # log in server logs if needed
        return None

def append_listing_history(email, date, car_text, price, tone, listing_snippet):
    sheet = get_sheet()
    if not sheet:
        return False
    ss = sheet.spreadsheet
    try:
        history = ss.worksheet("Listings History")
    except gspread.exceptions.WorksheetNotFound:
        history = ss.add_worksheet(title="Listings History", rows=2000, cols=6)
        history.append_row(["Email","Date","Car","Price","Tone","Listing"])
    try:
        history.append_row([email, date, car_text, price, tone, listing_snippet])
        return True
    except Exception:
        return False

