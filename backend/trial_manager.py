# backend/trial_manager.py
from datetime import datetime, timedelta
import pandas as pd
from backend.sheet_utils import (
    get_user_activity_data,
    upsert_to_sheet,
    get_sheet_data,
    get_dealership_profile,
    save_dealership_profile
)

# ----------------------
# CONFIG
# ----------------------
TRIAL_DAYS = 30
MAX_FREE_LISTINGS = 15  # Free trial limit
TRIAL_API = "trial"

# ----------------------
# INTERNAL UTILS
# ----------------------
def _safe_parse_date(value, default=None):
    """Safely parses a date value to datetime. Returns default if invalid."""
    try:
        return pd.to_datetime(value).to_pydatetime()
    except Exception:
        return default

def _get_user_activity_row(email: str):
    """Returns the latest activity row for a given email, or None if not found."""
    df = get_user_activity_data()
    if df.empty:
        return None
    df["Email_lower"] = df["Email"].astype(str).str.lower()
    matches = df[df["Email_lower"] == email.lower()]
    return matches.iloc[-1] if not matches.empty else None

# ----------------------
# CORE USER STATUS LOGIC
# ----------------------
def ensure_user_and_get_status(email: str, plan="Free Trial"):
    """
    Ensures user record exists and returns status, start/expiry dates, usage, and plan.
    Auto-updates the status to 'expired' if the trial is past expiry.
    """
    current_row = _get_user_activity_row(email)
    now = datetime.utcnow()

    if current_row is None or current_row.empty:
        # New user: create persistent record
        start_date = now
        expiry_date = start_date + timedelta(days=TRIAL_DAYS)
        usage_count = 0
        status = "new"

        upsert_to_sheet(
            "User_Activity",
            key_col="Email",
            data_dict={
                "Email": email,
                "Start_Date": start_date.strftime("%Y-%m-%d %H:%M:%S"),
                "Expiry_Date": expiry_date.strftime("%Y-%m-%d %H:%M:%S"),
                "Status": status,
                "Usage_Count": usage_count,
                "Plan": plan
            }
        )
        save_dealership_profile(email, {"Plan": plan, "Trial_Status": status})

    else:
        # Existing user: load persistent data
        start_date = _safe_parse_date(current_row.get("Start_Date"), now)
        expiry_date = _safe_parse_date(current_row.get("Expiry_Date"), start_date + timedelta(days=TRIAL_DAYS))
        usage_count = int(current_row.get("Usage_Count") or 0)
        plan = current_row.get("Plan") or plan
        status = current_row.get("Status") or "active"

        # Auto-update status if expired
        if now > expiry_date and status != "expired":
            status = "expired"
            upsert_to_sheet(
                "User_Activity",
                key_col="Email",
                data_dict={
                    "Email": email,
                    "Start_Date": start_date.strftime("%Y-%m-%d %H:%M:%S"),
                    "Expiry_Date": expiry_date.strftime("%Y-%m-%d %H:%M:%S"),
                    "Status": status,
                    "Usage_Count": usage_count,
                    "Plan": plan
                }
            )

    return status, expiry_date, start_date, usage_count, plan

# ----------------------
# USAGE MANAGEMENT
# ----------------------
def _update_activity_record(email: str, new_count: int, plan: str):
    """Update usage without resetting trial dates."""
    status, expiry_date, start_date, _, _ = ensure_user_and_get_status(email)
    data_to_save = {
        "Email": email,
        "Start_Date": start_date.strftime("%Y-%m-%d %H:%M:%S"),
        "Expiry_Date": expiry_date.strftime("%Y-%m-%d %H:%M:%S"),
        "Status": status,
        "Usage_Count": new_count,
        "Plan": plan
    }
    upsert_to_sheet("User_Activity", key_col="Email", data_dict=data_to_save)
    return new_count

def increment_usage(email: str, num=1):
    status, expiry_date, _, usage_count, plan = ensure_user_and_get_status(email)
    return _update_activity_record(email, usage_count + num, plan)

def decrement_listing_count(email: str, num=1):
    status, expiry_date, _, usage_count, plan = ensure_user_and_get_status(email)
    return _update_activity_record(email, max(usage_count - num, 0), plan)

def get_remaining_days(email: str):
    _, expiry_date, _, _, _ = ensure_user_and_get_status(email)
    return max(0, (expiry_date - datetime.utcnow()).days)

def reset_trial(email: str):
    start_date = datetime.utcnow()
    expiry_date = start_date + timedelta(days=TRIAL_DAYS)
    upsert_to_sheet(
        "User_Activity",
        key_col="Email",
        data_dict={
            "Email": email,
            "Start_Date": start_date.strftime("%Y-%m-%d %H:%M:%S"),
            "Expiry_Date": expiry_date.strftime("%Y-%m-%d %H:%M:%S"),
            "Status": "new",
            "Usage_Count": 0,
            "Plan": "Free Trial"
        }
    )

# ----------------------
# DEALERSHIP PROFILE & STATUS
# ----------------------
def get_dealership_status(email: str):
    status, expiry, _, usage_count, plan = ensure_user_and_get_status(email)
    profile_details = get_dealership_profile(email)
    remaining_listings = max(MAX_FREE_LISTINGS - usage_count, 0) if plan.lower() == "free trial" else 99
    return {
        "Email": email,
        "Trial_Status": status,
        "Trial_Expiry": expiry,
        "Usage_Count": usage_count,
        "Plan": plan,
        "Remaining_Listings": remaining_listings,
        "Name": profile_details.get("Name", ""),
        "Phone": profile_details.get("Phone", ""),
        "Location": profile_details.get("Location", "")
    }

def check_listing_limit(email: str):
    profile = get_dealership_status(email)
    return profile["Remaining_Listings"] > 0

# ----------------------
# MULTI-USER SEAT MANAGEMENT
# ----------------------
def get_plan_seat_limit(plan_name):
    plan_limits = {"free": 2, "premium": 3, "pro": 8, "platinum": 99}
    return plan_limits.get(plan_name.lower(), 1)

def can_user_login(email, plan_name):
    df_profiles = get_sheet_data("Dealership_Profiles")
    if df_profiles.empty or "Plan" not in df_profiles.columns:
        return True
    plan_users = df_profiles[df_profiles["Plan"].astype(str).str.lower() == plan_name.lower()]
    user_emails = plan_users["Email"].astype(str).str.lower().tolist()
    seat_limit = get_plan_seat_limit(plan_name)
    return email.lower() in user_emails or len(user_emails) < seat_limit

# ----------------------
# API HOOKS
# ----------------------
def api_get(url):
    """Placeholder for API GET request."""
    return {}

def api_post(url, payload):
    """Placeholder for API POST request."""
    return {}

def get_trial_status(email):
    res = api_get(f"{TRIAL_API}?email={email}")
    return res if res else {"status": "inactive"}

def start_free_trial(email):
    return api_post(TRIAL_API, {"action": "start", "email": email})

def increment_trial_usage(email, amount=1):
    return api_post(TRIAL_API, {"action": "increment_usage", "email": email, "amount": amount})

def validate_trial(email):
    return api_get(f"{TRIAL_API}?email={email}&validate=1")
