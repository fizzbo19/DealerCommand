# backend/trial_manager.py
import datetime
from backend.sheet_utils import get_sheet, append_listing_history

TRIAL_DAYS = 30

# ----------------------
# Trial Management
# ----------------------
def ensure_user_and_get_status(email):
    """
    Ensures a user exists in the sheet and returns trial status.
    Returns:
        status: "new", "active", or "expired"
        expiry: trial end date (datetime.date)
        used: number of listings generated
    """
    sheet = get_sheet()
    if not sheet:
        expiry = datetime.date.today() + datetime.timedelta(days=TRIAL_DAYS)
        return "new", expiry, 0

    records = sheet.get_all_records()
    for i, record in enumerate(records, start=2):
        if str(record.get("Email", "")).lower() == email.lower():
            try:
                expiry = datetime.datetime.strptime(record.get("Trial Ends"), "%Y-%m-%d").date()
            except Exception:
                expiry = datetime.date.today() + datetime.timedelta(days=TRIAL_DAYS)
            used = int(record.get("Listings Generated", 0))
            if datetime.date.today() > expiry:
                return "expired", expiry, used
            return "active", expiry, used

    # New user
    expiry = datetime.date.today() + datetime.timedelta(days=TRIAL_DAYS)
    try:
        sheet.append_row([email, str(datetime.date.today()), str(expiry), 0])
    except Exception:
        pass
    return "new", expiry, 0

def increment_usage(email, listing_text):
    """
    Increments the listing count for a user and logs the listing to history.
    Returns True if successful, False if trial expired or update fails.
    """
    sheet = get_sheet()
    if not sheet:
        return False

    records = sheet.get_all_records()
    for i, record in enumerate(records, start=2):
        if str(record.get("Email", "")).lower() == email.lower():
            try:
                expiry = datetime.datetime.strptime(record.get("Trial Ends"), "%Y-%m-%d").date()
            except Exception:
                expiry = datetime.date.today() + datetime.timedelta(days=TRIAL_DAYS)

            if datetime.date.today() > expiry:
                return False

            used = int(record.get("Listings Generated", 0)) + 1
            try:
                sheet.update_cell(i, 4, used)  # Column 4 = Listings Generated
                append_listing_history(email, str(datetime.date.today()), "-", "-", "-", listing_text[:300])
                return True
            except Exception:
                return False

    # User not found → create new row
    expiry = datetime.date.today() + datetime.timedelta(days=TRIAL_DAYS)
    try:
        sheet.append_row([email, str(datetime.date.today()), str(expiry), 1])
        append_listing_history(email, str(datetime.date.today()), "-", "-", "-", listing_text[:300])
        return True
    except Exception:
        return False

def get_trial_status(email):
    """
    Convenience wrapper to fetch trial status.
    """
    return ensure_user_and_get_status(email)

def get_recent_user_listings(email, limit=10):
    """
    Returns the most recent listings for a user from the history sheet.
    """
    sheet = get_sheet()
    if not sheet:
        return []

    ss = sheet.spreadsheet
    try:
        history = ss.worksheet("Listings History")
    except gspread.exceptions.WorksheetNotFound:
        return []

    rows = history.get_all_records()
    user_rows = [r for r in rows if str(r.get("Email", "")).lower() == email.lower()]
    return user_rows[::-1][:limit]


