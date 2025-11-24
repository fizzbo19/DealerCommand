import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from backend.sheet_utils import (
    get_inventory_for_user,
    get_social_media_data,
    get_sheet_data,
    append_to_google_sheet
)
from openai import OpenAI
import os
import json
import random

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
    from backend.trial_manager import increment_usage
    # Renamed from decrement_listing_count to increment_usage for clarity and consistency with trial_manager
    increment_usage(email, count) 

# ----------------------
# DEMO DATA GENERATOR
# ----------------------
def generate_demo_inventory(top_n=5):
    # Fixed dependency: numpy is not used here, replacing with random
    random.seed(42)
    makes = ["BMW", "Audi", "Mercedes", "Toyota", "Land Rover"]
    models = ["X5", "A3", "C-Class", "Corolla", "Discovery"]
    colors = ["Red", "Blue", "Black", "White"]
    demo_listings = []
    for i in range(top_n):
        demo_listings.append({
            "Make": random.choice(makes),
            "Model": random.choice(models),
            "Year": random.randint(2015, 2024),
            "Mileage": random.randint(5000, 80000),
            "Color": random.choice(colors),
            "Fuel": random.choice(["Petrol","Diesel","Hybrid"]),
            "Transmission": random.choice(["Manual","Automatic"]),
            "Price": f"£{random.randint(20000,50000)}",
            "Features": "Panoramic roof, heated seats, M Sport package",
            "Notes": "Full service history, finance available",
            "Timestamp": datetime.utcnow().isoformat(), # Use ISO format for consistency
            "Inventory_ID": str(uuid.uuid4())
        })
    return pd.DataFrame(demo_listings)

def generate_demo_social_data():
    random.seed(42)
    platforms = ["Instagram","TikTok","Facebook"]
    return pd.DataFrame({
        "Platform": random.choices(platforms, k=5),
        "Revenue": [random.randint(100, 1000) for _ in range(5)],
        "Reach": [random.randint(1000, 10000) for _ in range(5)],
        "Impressions": [random.randint(5000, 20000) for _ in range(5)]
    })

# ----------------------
# TOP RECOMMENDATIONS
# ----------------------
def get_platinum_top_recommendations(email, top_n=5, demo_mode=False):
    if demo_mode:
        return generate_demo_inventory(top_n).to_dict(orient="records")

    df = get_inventory_for_user(email)
    if df.empty:
        return []

    df = df.copy()
    df["Price_Num"] = pd.to_numeric(
        df.get("Price", 0).astype(str).str.replace("£","").str.replace(",",""),
        errors="coerce"
    ).fillna(0)
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
def get_platinum_dashboard(email, demo_mode=False):
    inventory_df = generate_demo_inventory() if demo_mode else get_inventory_for_user(email)
    social_df = generate_demo_social_data() if demo_mode else get_social_media_data(email)

    return {
        "Profile": {
            "Email": email,
            "Plan": "Platinum"
        },
        "Inventory_Count": len(inventory_df),
        "Remaining_Listings": get_platinum_remaining_listings(email),
        "Top_Recommendations": get_platinum_top_recommendations(email, demo_mode=demo_mode),
        "Social_Data": social_df.to_dict(orient="records")
    }

# ----------------------
# AI VIDEO SCRIPT GENERATOR
# ----------------------
def generate_ai_video_script(email, listing_data):
    make = listing_data.get('Make', 'Luxury Vehicle')
    model = listing_data.get('Model', 'Performance Sedan')
    features = listing_data.get('Features', 'premium sound, advanced driver assistance')
    
    if not ai_client:
        # Safe fallback if API key is missing
        return f"""
[SCENE: OPENING SHOT]
**VISUAL:** Dynamic shot of {make} {model}.
**AUDIO:** Energetic music.
**VOICEOVER:** Experience the thrill! This {model} is loaded with {features}. Contact us now!
"""

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
        # Fallback if API call fails (e.g., network error)
        return f"⚠️ Error generating script: {e}\n\n[Fallback: Contact DealerCommand today to book a test drive!]"

# ----------------------
# COMPETITOR MONITORING
# ----------------------
def competitor_monitoring(email, make="BMW", seed=1):
    """
    Generates a DataFrame showing competitive pricing intelligence for a given make.
    Simplified to take 'make' for demonstration purposes.
    """
    random.seed(seed)
    base_price = random.randint(45000, 55000)
    data = [
        {"Competitor": "Local Auto Co.", "Model": f"{make} X", "Price": base_price + random.randint(500, 2000), "Location": "Local"},
        {"Competitor": "Regional Hub", "Model": f"{make} Z", "Price": base_price - random.randint(500, 1500), "Location": "Online"},
        {"Competitor": "DealerCommand Avg", "Model": f"{make} Avg", "Price": base_price, "Location": "Market Average"}
    ]
    return pd.DataFrame(data)

# ----------------------
# WEEKLY CONTENT CALENDAR
# ----------------------
def generate_weekly_content_calendar(email, top_n=3, seed=1):
    random.seed(seed)
    inventory_df = generate_demo_inventory(top_n) # Use mock inventory for calendar content
    if inventory_df.empty:
        return pd.DataFrame()

    week_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    calendar_rows = []
    
    # Use top 3 cars from mock inventory
    top_listings = inventory_df.head(top_n).to_dict(orient='records')

    for i, listing in enumerate(top_listings):
        day_index = (i * 2) % 7 # Spread posts out
        
        # Post 1: Listing Spotlight
        calendar_rows.append({
            "Day": week_days[day_index],
            "Car": f"{listing.get('Make', '')} {listing.get('Model', '')}",
            "Content": f"Listing Spotlight: {listing.get('Color')} {listing.get('Make')} with {listing.get('Features')}! Asking Price: {listing.get('Price')}",
            "Platform": "Instagram/Facebook",
            "Post_Type": "Listing Spotlight"
        })
        
        # Post 2: Engagement/Tip
        day_index = (i * 2 + 1) % 7
        calendar_rows.append({
            "Day": week_days[day_index],
            "Car": "N/A",
            "Content": random.choice(["Quick Tip: Best practices for winter tire storage.", "Engage: What's your dream car color?", "Dealership News: Holiday service hours."]),
            "Platform": random.choice(["TikTok", "Instagram Story"]),
            "Post_Type": "Engagement/Tip"
        })

    df_calendar = pd.DataFrame(calendar_rows).sort_values(by="Day", key=lambda x: x.map({day: i for i, day in enumerate(week_days)}))
    return df_calendar

# ----------------------
# CUSTOM REPORT BUILDER SUPPORT
# ----------------------
def save_custom_report(email, report_config):
    """Placeholder to save report"""
    return True, "Report saved successfully."

def load_custom_reports(email):
    """Placeholder to load reports"""
    return []

def apply_report_filters(inventory_df, filters):
    """Placeholder to filter DataFrame"""
    return inventory_df