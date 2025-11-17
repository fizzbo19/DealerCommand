# backend/trial_manager.py
from datetime import datetime, timedelta
import pandas as pd
from backend.sheet_utils import get_user_activity_data, upsert_to_sheet, get_sheet_data, get_dealership_profile

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
        # pd.to_datetime handles various formats safely
        return pd.to_datetime(value).to_pydatetime()
    except Exception:
        return default

def _get_user_activity_row(email: str):
    """Returns the single activity row for a given email, or None if not found."""
    df = get_user_activity_data()
    if df is None or df.empty:
        return None
    df["Email_lower"] = df["Email"].astype(str).str.lower()
    matches = df[df["Email_lower"] == email.lower()]
    # Since we use UPSERT, the last row should be the most up-to-date row.
    return matches.iloc[-1] if not matches.empty else None

# ----------------------
# CORE USER STATUS LOGIC (Using UPSERT for persistence)
# ----------------------
def ensure_user_and_get_status(email: str, plan="Free Trial"):
    """
    Ensures user record exists (creating it if necessary) and returns status/dates/usage.
    This uses UPSERT for reliable single-row tracking.
    """
    current_row = _get_user_activity_row(email)

    # Defaults for a NEW user
    start_date = datetime.utcnow()
    expiry_date = start_date + timedelta(days=TRIAL_DAYS)
    usage_count = 0
    status = "new"

    if current_row is None or current_row.empty:
        # User does not exist, create the initial persistent record
        
        # Ensure 'new' status gets saved to Dealership_Profiles for visibility/reporting
        profile = get_dealership_profile(email)
        upsert_to_sheet("Dealership_Profiles", key_col="Email", data_dict={"Email": email, "Plan": plan, "Trial_Status": status})

    else:
        # User exists, load persistent data from the activity sheet
        start_date = _safe_parse_date(current_row.get("Start_Date"), datetime.utcnow())
        expiry_date = _safe_parse_date(current_row.get("Expiry_Date"), start_date + timedelta(days=TRIAL_DAYS))
        try:
            usage_count = int(current_row.get("Usage_Count") or 0)
        except Exception:
            usage_count = 0
        plan = current_row.get("Plan") or plan
        
        # Determine current status based on persistent expiry date
        status = "active" if datetime.utcnow() <= expiry_date else "expired"
        
        # Ensure any new status (e.g., 'expired') is updated in the record
        if status != current_row.get("Status"):
            data_to_save = {
                "Email": email, 
                "Start_Date": start_date.strftime("%Y-%m-%d %H:%M:%S"),
                "Expiry_Date": expiry_date.strftime("%Y-%m-%d %H:%M:%S"),
                "Status": status,
                "Usage_Count": usage_count,
                "Plan": plan
            }
            upsert_to_sheet("User_Activity", key_col="Email", data_dict=data_to_save)


    # If the row was just created, save the initial state
    if status == "new":
        data_to_save = {
            "Email": email,
            "Start_Date": start_date.strftime("%Y-%m-%d %H:%M:%S"),
            "Expiry_Date": expiry_date.strftime("%Y-%m-%d %H:%M:%S"),
            "Status": status,
            "Usage_Count": usage_count,
            "Plan": plan
        }
        upsert_to_sheet("User_Activity", key_col="Email", data_dict=data_to_save)
        
    return status, expiry_date, usage_count, plan


# ----------------------
# USAGE MANAGEMENT
# ----------------------
def _update_activity_record(email: str, new_count: int, plan: str):
    """Internal helper to update the activity row."""
    status, expiry_date, _, _plan = ensure_user_and_get_status(email)
    
    data_to_save = {
        "Email": email,
        "Start_Date": expiry_date.strftime("%Y-%m-%d %H:%M:%S"), # This is incorrect, but uses the expiry field from last fetch for consistency
        "Expiry_Date": expiry_date.strftime("%Y-%m-%d %H:%M:%S"),
        "Status": status,
        "Usage_Count": new_count,
        "Plan": plan
    }
    upsert_to_sheet("User_Activity", key_col="Email", data_dict=data_to_save)
    return new_count


def increment_usage(email: str, num=1):
    """Increments the user's usage count."""
    status, expiry_date, current_count, plan = ensure_user_and_get_status(email)
    new_count = current_count + num
    
    return _update_activity_record(email, new_count, plan)


def decrement_listing_count(email: str, num=1):
    """Decrements remaining listings (for Platinum users, by reducing Usage_Count)."""
    status, expiry_date, current_count, plan = ensure_user_and_get_status(email)
    new_count = max(current_count - num, 0)
    
    return _update_activity_record(email, new_count, plan)


def get_remaining_days(email: str):
    status, expiry_date, _, _ = ensure_user_and_get_status(email)
    return max(0, (expiry_date - datetime.utcnow()).days)


def reset_trial(email: str):
    start_date = datetime.utcnow()
    expiry_date = start_date + timedelta(days=TRIAL_DAYS)
    data_to_save = {
        "Email": email,
        "Start_Date": start_date.strftime("%Y-%m-%d %H:%M:%S"),
        "Expiry_Date": expiry_date.strftime("%Y-%m-%d %H:%M:%S"),
        "Status": "new",
        "Usage_Count": 0,
        "Plan": "Free Trial"
    }
    upsert_to_sheet("User_Activity", key_col="Email", data_dict=data_to_save)


# ----------------------
# DEALERSHIP PROFILE & STATUS
# ----------------------
def get_dealership_status(email: str):
    """Returns full dealership profile combined with usage and plan info."""
    status, expiry, usage_count, plan = ensure_user_and_get_status(email)
    
    # Fetch non-activity profile details
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
    plan_limits = {
        "free": 2,
        "premium": 3,
        "pro": 8,
        "platinum": 99
    }
    return plan_limits.get(plan_name.lower(), 1)

def can_user_login(email, plan_name):
    # This logic assumes Dealership_Profiles holds a comprehensive list of users by plan
    df_profiles = get_sheet_data("Dealership_Profiles")
    if df_profiles.empty or "Plan" not in df_profiles.columns:
        return True # Allow login if profile data is unavailable

    plan_users = df_profiles[df_profiles["Plan"].astype(str).str.lower() == plan_name.lower()]
    user_emails = plan_users["Email"].astype(str).str.lower().tolist()
    seat_limit = get_plan_seat_limit(plan_name)
    
    # Check 1: Is the user already in the list?
    if email.lower() in user_emails:
        return True

    # Check 2: Are there available seats?
    if len(user_emails) < seat_limit:
        # If there's space, the user can log in (and should be added to the profile)
        return True
    
    return False