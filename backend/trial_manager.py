# backend/trial_manager.py
from datetime import datetime, timedelta
import pandas as pd
from backend.sheet_utils import get_user_activity_data, get_sheet_data, append_to_google_sheet

# ----------------------
# CONFIG
# ----------------------
TRIAL_DAYS = 30
MAX_FREE_LISTINGS = 15  # Free trial limit

# ----------------------
# INTERNAL UTILS
# ----------------------
def _safe_parse_date(value, default=None):
    """Safely parses a date value to datetime. Returns default if invalid."""
    try:
        return pd.to_datetime(value).to_pydatetime()
    except Exception:
        return default

def _get_last_user_row(email: str):
    """Returns the last activity row for a given email, or None if not found."""
    df = get_user_activity_data()
    if df is None or df.empty:
        return None
    df["Email_lower"] = df["Email"].astype(str).str.lower()
    matches = df[df["Email_lower"] == email.lower()]
    return matches.iloc[-1] if not matches.empty else None

# ----------------------
# USER STATE LOGIC
# ----------------------
def ensure_user_and_get_status(email: str, plan="Free Trial"):
    """Ensures user exists and returns status, expiry date, usage count, plan."""
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
            "Usage_Count": usage_count,
            "Plan": plan
        })
        return status, expiry_date, usage_count

    start_date = _safe_parse_date(last_row.get("Start_Date"), datetime.utcnow())
    expiry_date = _safe_parse_date(last_row.get("Expiry_Date"), start_date + timedelta(days=TRIAL_DAYS))
    try:
        usage_count = int(last_row.get("Usage_Count") or 0)
    except Exception:
        usage_count = 0

    status = "active" if datetime.utcnow() <= expiry_date else "expired"
    return status, expiry_date, usage_count

# ----------------------
# USAGE MANAGEMENT
# ----------------------
def increment_usage(email: str, num=1):
    """Increments the user's usage count and updates their row."""
    last_row = _get_last_user_row(email)
    if last_row is None:
        ensure_user_and_get_status(email)
        last_row = _get_last_user_row(email)

    current_count = int(last_row.get("Usage_Count") or 0)
    new_count = current_count + num
    expiry_date = _safe_parse_date(last_row.get("Expiry_Date"), datetime.utcnow() + timedelta(days=TRIAL_DAYS))
    status = "active" if datetime.utcnow() <= expiry_date else "expired"

    append_to_google_sheet("User_Activity", {
        "Email": email,
        "Start_Date": last_row.get("Start_Date") or datetime.utcnow().strftime("%Y-%m-%d"),
        "Expiry_Date": expiry_date.strftime("%Y-%m-%d"),
        "Status": status,
        "Usage_Count": new_count,
        "Plan": last_row.get("Plan") or "Free Trial"
    })
    return new_count

def decrement_listing_count(email: str, num=1):
    """Decrements remaining listings (for Platinum users)."""
    last_row = _get_last_user_row(email)
    if last_row is None:
        ensure_user_and_get_status(email)
        last_row = _get_last_user_row(email)

    current_count = int(last_row.get("Usage_Count") or 0)
    new_count = max(current_count - num, 0)

    append_to_google_sheet("User_Activity", {
        "Email": email,
        "Start_Date": last_row.get("Start_Date"),
        "Expiry_Date": last_row.get("Expiry_Date"),
        "Status": last_row.get("Status"),
        "Usage_Count": new_count,
        "Plan": last_row.get("Plan") or "Free Trial"
    })
    return new_count

def get_remaining_days(email: str):
    last_row = _get_last_user_row(email)
    if last_row is None:
        return TRIAL_DAYS
    expiry_date = _safe_parse_date(last_row.get("Expiry_Date"))
    return max(0, (expiry_date - datetime.utcnow()).days) if expiry_date else 0

def reset_trial(email: str):
    start_date = datetime.utcnow()
    expiry_date = start_date + timedelta(days=TRIAL_DAYS)
    append_to_google_sheet("User_Activity", {
        "Email": email,
        "Start_Date": start_date.strftime("%Y-%m-%d"),
        "Expiry_Date": expiry_date.strftime("%Y-%m-%d"),
        "Status": "new",
        "Usage_Count": 0,
        "Plan": "Free Trial"
    })

# ----------------------
# DEALERSHIP PROFILE
# ----------------------
def get_dealership_status(email: str):
    """Returns full dealership profile with usage and plan info."""
    status, expiry, usage_count = ensure_user_and_get_status(email)
    last_row = _get_last_user_row(email)
    plan = last_row.get("Plan") if last_row else "Free Trial"

    remaining_listings = max(MAX_FREE_LISTINGS - usage_count, 0) if plan.lower() == "free trial" else 99  # Platinum or paid

    return {
        "Email": email,
        "Trial_Status": status,
        "Trial_Expiry": expiry,
        "Usage_Count": usage_count,
        "Plan": plan,
        "Remaining_Listings": remaining_listings
    }

def check_listing_limit(email: str):
    profile = get_dealership_status(email)
    return profile["Remaining_Listings"] > 0

# ----------------------
# MULTI-USER SEAT MANAGEMENT
# ----------------------
def get_plan_seat_limit(plan_name):
    plan_limits = {
        "free": 2,
        "premium": 3,
        "pro": 8,
        "platinum": 99
    }
    return plan_limits.get(plan_name.lower(), 1)

def can_user_login(email, plan_name):
    df_profiles = get_sheet_data("Dealership_Profiles")
    if df_profiles is None or df_profiles.empty:
        return True

    plan_users = df_profiles[df_profiles["Plan"].str.lower() == plan_name.lower()]
    user_emails = plan_users["Email"].str.lower().tolist()
    seat_limit = get_plan_seat_limit(plan_name)

    return email.lower() in user_emails or len(user_emails) < seat_limit

