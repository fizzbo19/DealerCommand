# backend/trial_manager.py

import datetime
from backend.sheet_utils import get_sheet, append_listing_history

TRIAL_DAYS = 90

def ensure_user_and_get_status(email):
    sheet = get_sheet()
    if not sheet:
        # treat as new user if no sheet configured
        expiry = datetime.date.today() + datetime.timedelta(days=TRIAL_DAYS)
        return "new", expiry, 0
    # find user row
    records = sheet.get_all_records()
    for i, r in enumerate(records, start=2):
        if str(r.get("Email","")).lower() == email.lower():
            expiry = None
            try:
                expiry = datetime.datetime.strptime(r.get("Trial Ends"), "%Y-%m-%d").date()
            except Exception:
                expiry = datetime.date.today() + datetime.timedelta(days=TRIAL_DAYS)
            used = int(r.get("Listings Generated", 0))
            if datetime.date.today() > expiry:
                return "expired", expiry, used
            return "active", expiry, used
    # not found -> create
    expiry = datetime.date.today() + datetime.timedelta(days=TRIAL_DAYS)
    try:
        sheet.append_row([email, str(datetime.date.today()), str(expiry), 0])
    except Exception:
        pass
    return "new", expiry, 0

def get_trial_status(email):
    # convenience wrapper
    return ensure_user_and_get_status(email)

def maybe_increment_usage(email, listing_text):
    sheet = get_sheet()
    if not sheet:
        return False
    records = sheet.get_all_records()
    for i, r in enumerate(records, start=2):
        if str(r.get("Email","")).lower() == email.lower():
            used = int(r.get("Listings Generated", 0))
            expiry = None
            try:
                expiry = datetime.datetime.strptime(r.get("Trial Ends"), "%Y-%m-%d").date()
            except Exception:
                expiry = datetime.date.today() + datetime.timedelta(days=TRIAL_DAYS)
            # if trial expired, do not increment
            if datetime.date.today() > expiry:
                return False
            used += 1
            try:
                sheet.update_cell(i, 4, used)
                # append to history
                append_listing_history(email, str(datetime.date.today()), "-", "-", "-", listing_text[:300])
                return True
            except Exception:
                return False
    # if not found, create record
    try:
        expiry = datetime.date.today() + datetime.timedelta(days=TRIAL_DAYS)
        sheet.append_row([email, str(datetime.date.today()), str(expiry), 1])
        append_listing_history(email, str(datetime.date.today()), "-", "-", "-", listing_text[:300])
        return True
    except Exception:
        return False

def get_recent_user_listings(email, limit=10):
    sheet = get_sheet()
    if not sheet:
        return []
    ss = sheet.spreadsheet
    try:
        history = ss.worksheet("Listings History")
    except gspread.exceptions.WorksheetNotFound:
        return []
    rows = history.get_all_records()
    user_rows = [r for r in rows if str(r.get("Email","")).lower() == email.lower()]
    return user_rows[::-1][:limit]
