# backend/trial_manager.py
from datetime import datetime, timedelta
import pandas as pd
from backend.sheet_utils import get_user_activity_data, append_to_google_sheet

# ----------------------
# CONFIG
# ----------------------
TRIAL_DAYS = 30
MAX_FREE_LISTINGS = 15

# ----------------------
# MAIN FUNCTIONS
# ----------------------
def ensure_user_and_get_status(email: str):
    """
    Checks if the user exists in 'User_Activity' sheet.
    Creates new user if not.
    Returns:
        status (str): "new", "active", "expired"
        expiry_date (datetime)
        usage_count (int)
    """
    df = get_user_activity_data()
    user_row = df[df["Email"].str.lower() == email.lower()]

    if user_row.empty:
        # New user → create trial
        start_date = datetime.today()
        expiry_date = start_date + timedelta(days=TRIAL_DAYS)
        usage_count = 0
        status = "new"

        # Append to sheet
        append_to_google_sheet("User_Activity", {
            "Email": email,
            "Start_Date": start_date.strftime("%Y-%m-%d"),
            "Expiry_Date": expiry_date.strftime("%Y-%m-%d"),
            "Status": status,
            "Usage_Count": usage_count
        })
    else:
        # Existing user
        user_row = user_row.iloc[0]
        start_date = pd.to_datetime(user_row["Start_Date"]) if pd.notnull(user_row["Start_Date"]) else datetime.today()
        expiry_date = pd.to_datetime(user_row["Expiry_Date"]) if pd.notnull(user_row["Expiry_Date"]) else start_date + timedelta(days=TRIAL_DAYS)
        usage_count = int(user_row["Usage_Count"]) if pd.notnull(user_row["Usage_Count"]) else 0

        # Determine status
        status = "active" if datetime.today() <= expiry_date else "expired"

    return status, expiry_date, usage_count

# ----------------------
def increment_usage(email: str, num=1):
    """
    Increment usage count for a user by `num`.
    Returns the new usage count.
    """
    df = get_user_activity_data()
    user_idx = df[df["Email"].str.lower() == email.lower()].index

    if not user_idx.empty:
        idx = user_idx[0]
        current_count = int(df.at[idx, "Usage_Count"]) if pd.notnull(df.at[idx, "Usage_Count"]) else 0
        new_count = current_count + num

        # Update sheet
        append_to_google_sheet("User_Activity", {
            "Email": email,
            "Start_Date": df.at[idx, "Start_Date"].strftime("%Y-%m-%d") if pd.notnull(df.at[idx, "Start_Date"]) else datetime.today().strftime("%Y-%m-%d"),
            "Expiry_Date": df.at[idx, "Expiry_Date"].strftime("%Y-%m-%d") if pd.notnull(df.at[idx, "Expiry_Date"]) else (datetime.today() + timedelta(days=TRIAL_DAYS)).strftime("%Y-%m-%d"),
            "Status": "active" if datetime.today() <= pd.to_datetime(df.at[idx, "Expiry_Date"]) else "expired",
            "Usage_Count": new_count
        })
        return new_count
    else:
        # If user somehow doesn't exist, create new
        status, expiry, usage_count = ensure_user_and_get_status(email)
        return increment_usage(email, num)

# ----------------------
def get_remaining_days(email: str):
    """
    Returns number of days left in trial.
    """
    df = get_user_activity_data()
    user_row = df[df["Email"].str.lower() == email.lower()]

    if user_row.empty:
        return 0

    expiry_date = pd.to_datetime(user_row.iloc[0]["Expiry_Date"])
    remaining = (expiry_date - datetime.today()).days
    return max(0, remaining)

# ----------------------
def reset_trial(email: str):
    """
    Reset trial for testing/admin purposes.
    """
    start_date = datetime.today()
    expiry_date = start_date + timedelta(days=TRIAL_DAYS)
    append_to_google_sheet("User_Activity", {
        "Email": email,
        "Start_Date": start_date.strftime("%Y-%m-%d"),
        "Expiry_Date": expiry_date.strftime("%Y-%m-%d"),
        "Status": "new",
        "Usage_Count": 0
    })
