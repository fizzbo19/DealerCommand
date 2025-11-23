import pandas as pd
from datetime import datetime, timedelta
import random
import os

# --- Assuming these functions exist in sheet_utils ---
from backend.sheet_utils import (
    get_user_activity_data,
    upsert_to_sheet,
    get_sheet_data,
    get_dealership_profile,
    save_dealership_profile,
    # api_get_dealership_profile removed as we use the local get_dealership_status
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
        # We need to handle both datetime objects and ISO strings from the sheet
        if isinstance(value, datetime): return value
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
    # Since we use UPSERT, the last row should be the most up-to-date row.
    return matches.iloc[-1] if not matches.empty else None

# ----------------------
# CORE USER STATUS LOGIC
# ----------------------
def ensure_user_and_get_status(email: str, plan="Free Trial"):
    """
    Ensures user record exists and returns status, start/expiry dates, usage, and plan.
    """
    current_row = _get_user_activity_row(email)
    now = datetime.utcnow()
    current_plan = plan # Default plan

    if current_row is None or current_row.empty:
        # New user: create persistent record
        start_date = now
        expiry_date = start_date + timedelta(days=TRIAL_DAYS)
        usage_count = 0
        status = "new"

    else:
        # Existing user: load persistent data
        start_date = _safe_parse_date(current_row.get("Start_Date"), now)
        # Use existing expiry date, falling back to 30 days from start date
        expiry_date = _safe_parse_date(current_row.get("Expiry_Date"), start_date + timedelta(days=TRIAL_DAYS))
        usage_count = int(current_row.get("Usage_Count") or 0)
        current_plan = current_row.get("Plan") or plan
        status = current_row.get("Status") or "active"

        # Auto-update status if expired
        if now > expiry_date and status != "expired":
            status = "expired"

    # Save/Update the record using ISO format for maximum precision
    data_to_save = {
        "Email": email,
        "Start_Date": start_date.isoformat(),
        "Expiry_Date": expiry_date.isoformat(),
        "Status": status,
        "Usage_Count": usage_count,
        "Plan": current_plan
    }
    upsert_to_sheet("User_Activity", key_col="Email", data_dict=data_to_save)
    
    # Ensure profile sheet reflects plan (for seat management)
    save_dealership_profile(email, {"Plan": current_plan, "Trial_Status": status})

    # Return status, expiry, usage, and plan (using the validated, final values)
    return status, expiry_date, usage_count, current_plan

# ----------------------
# USAGE MANAGEMENT
# ----------------------
def _update_activity_record(email: str, new_count: int, plan: str):
    """Update usage without resetting trial dates."""
    # Ensure user exists and get current status/dates
    status, expiry_date, _, current_plan = ensure_user_and_get_status(email, plan)
    
    # Get the specific Start Date from the sheet (necessary for consistency)
    current_row = _get_user_activity_row(email)
    start_date = _safe_parse_date(current_row.get("Start_Date"), datetime.utcnow())

    data_to_save = {
        "Email": email,
        # Save dates as ISO strings to prevent accidental parsing/formatting issues
        "Start_Date": start_date.isoformat(),
        "Expiry_Date": expiry_date.isoformat(),
        "Status": status,
        "Usage_Count": new_count,
        "Plan": current_plan
    }
    upsert_to_sheet("User_Activity", key_col="Email", data_dict=data_to_save)
    return new_count

def increment_usage(email: str, num=1):
    """Increments the listing usage count."""
    status, expiry_date, usage_count, plan = ensure_user_and_get_status(email)
    return _update_activity_record(email, usage_count + num, plan)

def decrement_listing_count(email: str, num=1):
    """Decrements remaining listings (for Platinum users, by reducing Usage_Count)."""
    status, expiry_date, usage_count, plan = ensure_user_and_get_status(email)
    return _update_activity_record(email, max(usage_count - num, 0), plan)

def get_remaining_days(email: str):
    _, expiry_date, _, _ = ensure_user_and_get_status(email)
    return max(0, (expiry_date - datetime.utcnow()).days)

def reset_trial(email: str):
    start_date = datetime.utcnow()
    expiry_date = start_date + timedelta(days=TRIAL_DAYS)
    upsert_to_sheet(
        "User_Activity",
        key_col="Email",
        data_dict={
            "Email": email,
            "Start_Date": start_date.isoformat(),
            "Expiry_Date": expiry_date.isoformat(),
            "Status": "new",
            "Usage_Count": 0,
            "Plan": "Free Trial"
        }
    )

# ----------------------
# DEALERSHIP PROFILE & STATUS
# ----------------------
def get_dealership_status(email: str):
    """
    Returns full dealership profile combined with persistent usage and plan info.
    This is the main function called by the frontend.
    """
    status, expiry, usage_count, base_plan = ensure_user_and_get_status(email)
    profile_details = get_dealership_profile(email)

    # Determine the effective plan (Platinum during active trial)
    effective_plan = 'platinum' if datetime.utcnow() <= expiry else base_plan
    
    remaining_listings = max(MAX_FREE_LISTINGS - usage_count, 0) if effective_plan.lower() == "free trial" else 99

    return {
        "Email": email,
        "Trial_Status": status,
        "Trial_Expiry": expiry,
        "Usage_Count": usage_count,
        "Plan": effective_plan,
        "Remaining_Listings": remaining_listings,
        "Name": profile_details.get("Name", ""),
        "Phone": profile_details.get("Phone", ""),
        "Location": profile_details.get("Location", "")
    }

def check_listing_limit(email: str):
    """Checks the listing limit using the local, robust data."""
    profile = get_dealership_status(email) # Use the local, robust function
    return profile.get("Remaining_Listings", 0) > 0

# ----------------------
# MULTI-USER SEAT MANAGEMENT
# ----------------------
def get_plan_seat_limit(plan_name):
    plan_limits = {"free": 2, "premium": 3, "pro": 8, "platinum": 99}
    return plan_limits.get(plan_name.lower(), 1)

def can_user_login(email, plan_name):
    """Checks if the user can log in based on their base plan's seat limit."""
    df_profiles = get_sheet_data("Dealership_Profiles")
    
    if df_profiles.empty or "Plan" not in df_profiles.columns:
        return True # Allow login if profile data is unavailable

    # Get the user's base plan from the Dealership_Profiles sheet (not the effective trial status)
    user_row = df_profiles[df_profiles["Email"].astype(str).str.lower() == email.lower()]
    base_plan = user_row.iloc[0].get("Plan", "Free Trial") if not user_row.empty else "Free Trial"
    
    plan_users = df_profiles[df_profiles["Plan"].astype(str).str.lower() == base_plan.lower()]
    user_emails = plan_users["Email"].astype(str).str.lower().tolist()
    seat_limit = get_plan_seat_limit(base_plan)
    
    # Check 1: Is the user already in the list?
    if email.lower() in user_emails:
        return True

    # Check 2: Are there available seats for this plan?
    if len(user_emails) < seat_limit:
        return True
    
    return False

# ----------------------
# API HOOKS (Removed unused functions for cleanup)
# ----------------------
# Note: api_get_dealership_profile, api_get, api_post, get_trial_status, start_free_trial, increment_trial_usage, validate_trial removed as they were either duplicates or unused placeholders.