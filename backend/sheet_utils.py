# backend/sheet_utils.py
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.trial_manager import check_trial_status
from backend.sheet_utils import append_to_google_sheet



def get_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials_info = json.loads(st.secrets["google"]["credentials_json"])
    creds = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(
        "https://docs.google.com/spreadsheets/d/12UDiRnjQXwxcHFjR3SWdz8lB45-OTGHBzm3YVcExnsQ/edit"
    ).sheet1
    return sheet

SHEET_URL = "https://docs.google.com/spreadsheets/d/12UDiRnjQXwxcHFjR3SWdz8lB45-OTGHBzm3YVcExnsQ/edit"

def get_sheet():
    """
    Connect to the Google Sheet using service account credentials.
    Make sure your credentials JSON file is stored in backend/ and named service_account.json
    """
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials_path = os.path.join(os.path.dirname(__file__), "service_account.json")

    if not os.path.exists(credentials_path):
        raise FileNotFoundError("Google service_account.json not found in backend folder")

    creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(SHEET_URL).sheet1
    return sheet


def append_to_google_sheet(email, data_dict):
    """
    Append car listing details to the Google Sheet.
    """
    sheet = get_sheet()
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

