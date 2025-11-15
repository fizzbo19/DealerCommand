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
# INTERNAL UTILS
# ----------------------
def _safe_parse_date(value, default=None):
    """
    Safely parses a date value to datetime. Returns default if invalid.
    """
    try:
        return pd.to_datetime(value).to_pydatetime()
    except Exception:
        return default


def _get_last_user_row(email: str):
    """
    Returns the last activity row for a given email, or None if not found.
    """
    df = get_user_activity_data()

    if df is None or df.empty:
        return None

    df["Email_lower"] = df["Email"].astype(str).str.lower()
    matches = df[df["Email_lower"] == email.lower()]
    return matches.iloc[-1] if not matches.empty else None


# ----------------------
# MAIN USER STATE LOGIC
# ----------------------
def ensure_user_and_get_status(email: str):
    """
    Ensures user exists in User_Activity sheet and returns:
      - status (new/active/expired)
      - expiry_date (datetime)
      - usage_count (int)
    """
    last_row = _get_last_user_row(email)

    # If no record exists, create one
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

    # Parse fields safely
    start_date = _safe_parse_date(last_row.get("Start_Date"), datetime.utcnow())
    expiry_date = _safe_parse_date(last_row.get("Expiry_Date"), start_date + timedelta(days=TRIAL_DAYS))

    # Usage count
    try:
        usage_count = int(last_row.get("Usage_Count") or 0)
    except Exception:
        usage_count = 0

    now = datetime.utcnow()
    status = "active" if now <= expiry_date else "expired"

    return status, expiry_date, usage_count


# ----------------------
# USAGE MANAGEMENT
# ----------------------
def increment_usage(email: str, num=1):
    """
    Increments the user's usage count by `num`, updates their row, and returns new count.
    """
    last_row = _get_last_user_row(email)

    if last_row is None:
        ensure_user_and_get_status(email)
        last_row = _get_last_user_row(email)

    # Current usage
    try:
        current_count = int(last_row.get("Usage_Count") or 0)
    except Exception:
        current_count = 0

    new_count = current_count + num

    # Ensure expiry date exists
    expiry_date = _safe_parse_date(
        last_row.get("Expiry_Date"),
        datetime.utcnow() + timedelta(days=TRIAL_DAYS)
    )

    # Determine status
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
    Returns number of days left in the trial.
    """
    last_row = _get_last_user_row(email)
    if last_row is None:
        return TRIAL_DAYS

    expiry_date = _safe_parse_date(last_row.get("Expiry_Date"))
    if expiry_date is None:
        return 0

    remaining = (expiry_date - datetime.utcnow()).days
    return max(0, remaining)


def reset_trial(email: str):
    """
    Completely resets a user's trial.
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
# PUBLIC ACCESS HELPERS
# ----------------------
def get_dealership_status(email: str):
    """
    Returns full dealership trial profile including:
      - Email
      - Trial_Status
      - Trial_Expiry
      - Usage_Count
      - Plan (currently 'Free Trial')
      - Remaining_Listings
    """
    status, expiry, usage_count = ensure_user_and_get_status(email)

    remaining_listings = max(MAX_FREE_LISTINGS - usage_count, 0)

    return {
        "Email": email,
        "Trial_Status": status,
        "Trial_Expiry": expiry,
        "Usage_Count": usage_count,
        "Plan": "Free Trial",
        "Remaining_Listings": remaining_listings
    }


def check_listing_limit(email: str):
    """
    Returns True if dealer can add another listing, otherwise False.
    """
    profile = get_dealership_status(email)
    return profile["Remaining_Listings"] > 0


