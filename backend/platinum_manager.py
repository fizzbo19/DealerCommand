# backend/platinum_manager.py
import pandas as pd
from datetime import datetime
from backend.sheet_utils import get_inventory_for_user, get_social_media_data, get_sheet_data, append_to_google_sheet
from openai import OpenAI
import os

# ----------------------
# AI CLIENT
# ----------------------
API_KEY = os.environ.get("OPENAI_API_KEY")
ai_client = OpenAI(api_key=API_KEY) if API_KEY else None

# ----------------------
# PLATINUM CHECK
# ----------------------
def is_platinum(email):
    from backend.trial_manager import get_dealership_status
    plan = get_dealership_status(email).get("Plan", "").lower()
    return plan == "platinum"

# ----------------------
# LISTING USAGE
# ----------------------
def can_add_listing(email):
    from backend.trial_manager import get_dealership_status
    status = get_dealership_status(email)
    remaining = status.get("Remaining_Listings", 0)
    return remaining > 0 or is_platinum(email)

def increment_platinum_usage(email, count=1):
    # In a full system, update sheet or DB to decrement Remaining_Listings
    from backend.trial_manager import decrement_listing_count
    decrement_listing_count(email, count)

# ----------------------
# TOP RECOMMENDATIONS
# ----------------------
def get_platinum_top_recommendations(email, top_n=5):
    df = get_inventory_for_user(email)
    if df.empty:
        return []

    df = df.copy()
    # Score by price (higher better) + recency
    df["Price_Num"] = pd.to_numeric(df.get("Price", 0).replace("£","").replace(",",""), errors="coerce").fillna(0)
    df["Timestamp"] = pd.to_datetime(df.get("Timestamp", datetime.utcnow()), errors="coerce")
    df = df.sort_values(["Price_Num", "Timestamp"], ascending=[False, False])
    top_df = df.head(top_n)
    return top_df.to_dict(orient="records")

def get_platinum_remaining_listings(email):
    from backend.trial_manager import get_dealership_status
    return get_dealership_status(email).get("Remaining_Listings", 0)

# ----------------------
# DASHBOARD
# ----------------------
def get_platinum_dashboard(email):
    return {
        "Profile": {
            "Email": email,
            "Plan": "Platinum"
        },
        "Inventory_Count": len(get_inventory_for_user(email)),
        "Remaining_Listings": get_platinum_remaining_listings(email),
        "Top_Recommendations": get_platinum_top_recommendations(email),
        "Social_Data": get_social_media_data(email)
    }

# ----------------------
# AI VIDEO SCRIPT GENERATOR
# ----------------------
def generate_ai_video_script(email, listing_data):
    if not ai_client:
        return "⚠️ OpenAI API key not configured."
    prompt = f"""
You are a professional automotive copywriter. Create a 90–120 second AI video script for the following car listing:

Make: {listing_data.get('Make')}
Model: {listing_data.get('Model')}
Year: {listing_data.get('Year')}
Mileage: {listing_data.get('Mileage')}
Color: {listing_data.get('Color')}
Fuel: {listing_data.get('Fuel')}
Transmission: {listing_data.get('Transmission')}
Price: {listing_data.get('Price')}
Features: {listing_data.get('Features')}
Dealer Notes: {listing_data.get('Notes')}

Write in an engaging, friendly, and persuasive tone for social media. Include emojis and call-to-actions.
"""
    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content":"You are a top-tier automotive copywriter."},
                {"role":"user","content":prompt}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content.strip() if response and getattr(response, "choices", None) else ""
    except Exception as e:
        return f"⚠️ Error generating script: {e}"

# ----------------------
# COMPETITOR MONITORING
# ----------------------
def competitor_monitoring(email, competitor_csv=None, sheet_name=None):
    if competitor_csv:
        df = pd.read_csv(competitor_csv)
    elif sheet_name:
        df = get_sheet_data(sheet_name)
    else:
        return pd.DataFrame(), {"Error": "No competitor data provided"}

    if df.empty:
        return pd.DataFrame(), {"Error": "No competitor listings found"}

    df["Price"] = pd.to_numeric(df.get("Price", 0), errors="coerce").fillna(0)
    summary = {
        "Total_Competitors": len(df),
        "Avg_Price": round(df["Price"].mean(), 2),
        "Min_Price": df["Price"].min(),
        "Max_Price": df["Price"].max(),
        "Most_Common_Make": df["Make"].mode()[0] if not df["Make"].mode().empty else "",
        "Most_Common_Model": df["Model"].mode()[0] if not df["Model"].mode().empty else ""
    }
    return df, summary

# ----------------------
# WEEKLY CONTENT CALENDAR
# ----------------------
def generate_weekly_content_calendar(email, plan="platinum"):
    inventory_df = get_inventory_for_user(email)
    if inventory_df.empty:
        return pd.DataFrame(), "No inventory to generate content calendar."

    top_listings = get_platinum_top_recommendations(email, top_n=5)
    week_days = ["Monday","Wednesday","Friday"]
    calendar_rows = []

    for i, listing in enumerate(top_listings):
        calendar_rows.append({
            "Day": week_days[i % len(week_days)],
            "Car": f"{listing['Year']} {listing['Make']} {listing['Model']}",
            "Caption": f"Check out this {listing['Color']} {listing['Make']} {listing['Model']}! 🚗🔥 #CarFundo #PlatinumListing",
            "Platform": "Instagram/TikTok",
            "Post_Type": "Listing Spotlight"
        })

    df_calendar = pd.DataFrame(calendar_rows)
    return df_calendar, f"Weekly content calendar generated with {len(df_calendar)} posts."
