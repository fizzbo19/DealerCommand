# backend/sheet_utils.py
import json, os
import gspread
from google.oauth2.service_account import Credentials

SHEET_URL = "https://docs.google.com/spreadsheets/d/12UDiRnjQXwxcHFjR3SWdz8lB45-OTGHBzm3YVcExnsQ/edit"

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

