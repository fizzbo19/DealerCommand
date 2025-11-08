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
    today = datetime.date.today()

    if not sheet:
        expiry = today + datetime.timedelta(days=TRIAL_DAYS)
        return "new", expiry, 0

    records = sheet.get_all_records()
    for i, record in enumerate(records, start=2):
        if str(record.get("Email", "")).lower() == email.lower():
            try:
                expiry = datetime.datetime.strptime(record.get("Trial Ends"), "%Y-%m-%d").date()
            except Exception:
                expiry = today + datetime.timedelta(days=TRIAL_DAYS)
            used = int(record.get("Listings Generated", 0))
            if today > expiry:
                return "expired", expiry, used
            return "active", expiry, used

    # New user → append to sheet
    expiry = today + datetime.timedelta(days=TRIAL_DAYS)
    try:
        sheet.append_row([email, str(today), str(expiry), 0])
    except Exception as e:
        print(f"⚠️ Could not append new trial user: {e}")
    return "new", expiry, 0


# ----------------------
# Increment Listings Usage
# ----------------------
def increment_usage(email, listing_text):
    """
    Increments the listing count for a user and logs the listing to history.
    Returns True if successful, False if trial expired or update fails.
    """
    sheet = get_sheet()
    today = datetime.date.today()

    if not sheet:
        return False

    records = sheet.get_all_records()
    for i, record in enumerate(records, start=2):
        if str(record.get("Email", "")).lower() == email.lower():
            try:
                expiry = datetime.datetime.strptime(record.get("Trial Ends"), "%Y-%m-%d").date()
            except Exception:
                expiry = today + datetime.timedelta(days=TRIAL_DAYS)

            if today > expiry:
                return False

            used = int(record.get("Listings Generated", 0)) + 1
            try:
                # Update listings count
                sheet.update_cell(i, 4, used)  # Column 4 = Listings Generated
                # Log listing in history sheet
                append_listing_history(email, str(today), "-", "-", "-", listing_text[:300])
                return True
            except Exception as e:
                print(f"⚠️ Error updating usage: {e}")
                return False

    # User not found → create new row
    try:
        sheet.append_row([email, str(today), str(today + datetime.timedelta(days=TRIAL_DAYS)), 1])
        append_listing_history(email, str(today), "-", "-", "-", listing_text[:300])
        return True
    except Exception as e:
        print(f"⚠️ Could not create new user row: {e}")
        return False


# ----------------------
# Convenience Wrappers
# ----------------------
def get_trial_status(email):
    """Return trial status, expiry date, and usage count."""
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
    except Exception:
        return []

    rows = history.get_all_records()
    user_rows = [r for r in rows if str(r.get("Email", "")).lower() == email.lower()]
    return user_rows[::-1][:limit]
