# backend/trial_manager.py
from datetime import datetime, timedelta
import pandas as pd
from backend.sheet_utils import get_user_activity_data, append_to_google_sheet

# ----------------------
# CONFIG
# ----------------------
TRIAL_DAYS = 30
MAX_FREE_LISTINGS = 15  # Free trial limit

# ----------------------
# UTILITY FUNCTIONS
# ----------------------
def _get_last_user_row(email: str):
    """
    Returns the last row of user activity for an email or None if not found.
    """
    df = get_user_activity_data()
    df["Email_lower"] = df["Email"].astype(str).str.lower()
    email_lower = email.lower()
    matches = df[df["Email_lower"] == email_lower]
    if matches.empty:
        return None
    return matches.iloc[-1]

def ensure_user_and_get_status(email: str):
    """
    Ensures user exists in 'User_Activity', returns:
    - status (new/active/expired)
    - expiry_date (datetime)
    - usage_count (int)
    """
    last_row = _get_last_user_row(email)
    if last_row is None:
        start_date = datetime.utcnow()
        expiry_date = start_date + timedelta(days=TRIAL_DAYS)
        usage_count = 0
        status = "new"
        append_to_google_sheet("User_Activity", {
            "Email": email,
            "Start_Date": start_date.strftime("%Y-%m-%d"),
            "Expiry_Date": expiry_date.strftime("%Y-%m-%d"),
            "Status": status,
            "Usage_Count": usage_count
        })
        return status, expiry_date, usage_count

    try:
        start_date = pd.to_datetime(last_row.get("Start_Date")).to_pydatetime()
    except Exception:
        start_date = datetime.utcnow()

    try:
        expiry_date = pd.to_datetime(last_row.get("Expiry_Date")).to_pydatetime()
    except Exception:
        expiry_date = start_date + timedelta(days=TRIAL_DAYS)

    try:
        usage_count = int(last_row.get("Usage_Count", 0) or 0)
    except Exception:
        usage_count = 0

    now = datetime.utcnow()
    status = "active" if now <= expiry_date else "expired"

    return status, expiry_date, usage_count

# ----------------------
# TRIAL MANAGEMENT
# ----------------------
def increment_usage(email: str, num=1):
    """
    Increments the user's listing usage by `num`.
    Returns the new usage count.
    """
    last_row = _get_last_user_row(email)
    if last_row is None:
        ensure_user_and_get_status(email)
        return increment_usage(email, num)

    try:
        current_count = int(last_row.get("Usage_Count", 0) or 0)
    except Exception:
        current_count = 0
    new_count = current_count + num

    try:
        expiry_date = pd.to_datetime(last_row.get("Expiry_Date")).to_pydatetime()
    except Exception:
        expiry_date = datetime.utcnow() + timedelta(days=TRIAL_DAYS)

    status = "active" if datetime.utcnow() <= expiry_date else "expired"

    append_to_google_sheet("User_Activity", {
        "Email": email,
        "Start_Date": last_row.get("Start_Date") or datetime.utcnow().strftime("%Y-%m-%d"),
        "Expiry_Date": expiry_date.strftime("%Y-%m-%d"),
        "Status": status,
        "Usage_Count": new_count
    })

    return new_count

def get_remaining_days(email: str):
    """
    Returns number of days left in trial for a dealership.
    """
    last_row = _get_last_user_row(email)
    if last_row is None:
        return TRIAL_DAYS

    try:
        expiry_date = pd.to_datetime(last_row.get("Expiry_Date"))
    except Exception:
        return 0

    remaining = (expiry_date - pd.Timestamp.utcnow()).days
    return max(0, int(remaining))

def reset_trial(email: str):
    """
    Resets trial for a dealership.
    """
    start_date = datetime.utcnow()
    expiry_date = start_date + timedelta(days=TRIAL_DAYS)
    append_to_google_sheet("User_Activity", {
        "Email": email,
        "Start_Date": start_date.strftime("%Y-%m-%d"),
        "Expiry_Date": expiry_date.strftime("%Y-%m-%d"),
        "Status": "new",
        "Usage_Count": 0
    })

# ----------------------
# DEALERSHIP STATUS HELPERS
# ----------------------
def get_dealership_status(email: str):
    """
    Returns full dealership profile including:
    - Email
    - Trial_Status
    - Trial_Expiry
    - Usage_Count
    - Plan (currently free trial)
    - Remaining_Listings
    """
    status, expiry, usage_count = ensure_user_and_get_status(email)
    remaining = max(MAX_FREE_LISTINGS - usage_count, 0)

    return {
        "Email": email,
        "Trial_Status": status,
        "Trial_Expiry": expiry,
        "Usage_Count": usage_count,
        "Plan": "Free Trial",
        "Remaining_Listings": remaining
    }

def check_listing_limit(email: str):
    """
    Returns True if dealership can add another listing, False if limit exceeded.
    """
    profile = get_dealership_status(email)
    return profile["Remaining_Listings"] > 0

