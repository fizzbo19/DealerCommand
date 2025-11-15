# frontend/app.py
import sys, os, io, json
from datetime import datetime
import streamlit as st
import pandas as pd
from openai import OpenAI

# ---------------------------------------------------------
# FIXED / CLEANED PYTHON PATH SETUP
# ---------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.append(BASE_DIR)
sys.path.append(BACKEND_DIR)

# ---------------------------------------------------------
# Local Imports (SAFE)
# ---------------------------------------------------------
from backend.trial_manager import get_dealership_status, check_listing_limit, increment_usage
from backend.sheet_utils import append_to_google_sheet, get_sheet_data
from backend.stripe_utils import create_checkout_session
from backend.show_analytics_dashboard import show_analytics_dashboard  # ✅ This now works

# ---------------------------------------------------------
# Google Drive Upload (graceful fail)
# ---------------------------------------------------------
try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    GOOGLE_API_AVAILABLE = True
except ModuleNotFoundError:
    GOOGLE_API_AVAILABLE = False
    print("⚠️ googleapiclient not installed. Drive uploads disabled.")


def upload_image_to_drive(file_obj, filename, folder_id=None):
    if not GOOGLE_API_AVAILABLE:
        st.warning("⚠️ Google Drive upload unavailable. Install google-api-python-client.")
        return None
    try:
        raw = os.environ.get("GOOGLE_CREDENTIALS_JSON") or os.environ.get("GOOGLE_CREDENTIALS")
        if not raw:
            st.warning("⚠️ GOOGLE_CREDENTIALS not set in environment.")
            return None

        info = json.loads(raw)
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/drive"])
        service = build('drive', 'v3', credentials=creds)

        media = MediaIoBaseUpload(io.BytesIO(file_obj.read()), mimetype="image/png")
        file_metadata = {"name": filename}
        if folder_id:
            file_metadata["parents"] = [folder_id]

        uploaded = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        ).execute()

        file_id = uploaded.get("id")
        service.permissions().create(
            fileId=file_id,
            body={"role": "reader", "type": "anyone"}
        ).execute()

        return f"https://drive.google.com/uc?id={file_id}"

    except Exception as e:
        print(f"⚠️ Failed to upload image: {e}")
        return None


# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(page_title="DealerCommand AI | Smart Listings", layout="wide", page_icon="🚗")

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
LOGO_FILE = os.path.join(ASSETS_DIR, "dealercommand_logov1.png")

# Sidebar logo
if os.path.exists(LOGO_FILE):
    st.sidebar.image(LOGO_FILE, width=160, caption="DealerCommand AI")
else:
    st.sidebar.markdown("**DealerCommand AI**")

st.markdown('<h2 style="text-align:center;">🚗 DealerCommand AI</h2>', unsafe_allow_html=True)
st.markdown('<div class="hero-sub">Create high-converting, SEO-optimised car listings in seconds with AI.</div>', unsafe_allow_html=True)

# ---------------------------------------------------------
# API Key Check
# ---------------------------------------------------------
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    st.error("⚠️ Missing OpenAI API key. Set `OPENAI_API_KEY` in environment.")
    st.stop()

# ---------------------------------------------------------
# Dealership Email Login
# ---------------------------------------------------------
user_email = st.text_input("📧 Dealership email", placeholder="e.g. sales@autohub.co.uk")
if not user_email:
    st.info("👋 Enter your dealership email above to start your 30-day free trial.")
    st.stop()

# ---------------------------------------------------------
# Fetch Profile
# ---------------------------------------------------------
profile = get_dealership_status(user_email)
status = profile["Trial_Status"]
expiry_date = profile["Trial_Expiry"]
usage_count = profile["Usage_Count"]
remaining_listings = profile["Remaining_Listings"]
is_active = status in ["active", "new"]
remaining_days = max((expiry_date - datetime.utcnow()).days, 0) if expiry_date else 0

# ---------------------------------------------------------
# First-time Dealer Info
# ---------------------------------------------------------
if status == "new":
    st.info("👋 Welcome! Please provide your dealership info to start your trial.")
    with st.form("dealer_info_form"):
        dealer_name = st.text_input("Dealership Name")
        dealer_phone = st.text_input("Phone Number")
        dealer_location = st.text_input("Location / City")
        submitted = st.form_submit_button("Save Info")
        if submitted:
            append_to_google_sheet("Dealership_Profiles", {
                "Email": user_email,
                "Name": dealer_name,
                "Phone": dealer_phone,
                "Location": dealer_location
            })
            st.success("✅ Dealership info saved!")

# ---------------------------------------------------------
# Sidebar Tabs
# ---------------------------------------------------------
sidebar_tabs = st.sidebar.tabs(["🎯 Trial Overview", "💳 Upgrade Plans", "⚙️ User Settings"])

# Trial Overview
with sidebar_tabs[0]:
    st.markdown("### 🎯 Your DealerCommand Trial")
    st.markdown(f"**👤 Email:** `{user_email}`")
    st.markdown(f"**📊 Listings Used:** `{usage_count}` / 15")
    st.progress(int(min((usage_count / 15) * 100, 100)))

    if is_active:
        st.markdown(f"**🟢 Status:** Active Trial")
        st.markdown(f"**⏳ Days Remaining:** `{remaining_days}` days")
        st.markdown(f"**📅 Ends On:** `{expiry_date.strftime('%B %d, %Y')}`")
        st.markdown(f"**📌 Remaining Listings:** `{remaining_listings}`")
    else:
        st.error("🚫 Your trial has expired. Upgrade to continue using DealerCommand.")

# Upgrade Plans

    # Sidebar: Plans Info
with st.sidebar.expander("💳 See Our Plans"):
    st.markdown("### ✨ Premium – Free for 30 Days, then £49.99/mo")
    st.markdown("""
- Social Media Analytics Dashboard
- Instagram/TikTok post performance
- Basic AI captions (5 per day)
- Inventory Upload (Google Sheet)
- Inventory Overview (20 cars max)
- Weekly Dealer Report (Email)
- 1 User Seat
**Best for:** Dealers testing AI but not fully committed.
""")

    st.markdown("### 🚀 Pro – £99.99/mo")
    st.markdown("""
- Everything in Premium, plus:
- Full Social Analytics + Deep Insights
- Dealer Performance Score (Daily)
- Inventory Dashboard (Unlimited Cars)
- AI Video Script Generator
- Compare Cars Analytics Module
- Export to CSV & Google Sheets Sync
- Custom AI Recommendations (Daily)
- Competitor Monitoring (Local Market)
- Auto-Scheduled Weekly Content Calendar
- 3 User Seats
**Best for:** Dealers who want reliable automation & sales insights.
""")

    st.markdown("### 👑 Platinum – £179.99/mo")
    st.markdown("""
- Everything in Pro, plus:
- Custom Charts & Analytics Modules
- Market Price Intelligence
- Best Price to List (AI Appraisal Tool)
- Automated Sales Forecasting
- Branding Kit
- White-Label Dealer Portal
- Priority Support
- Dedicated Account Setup
- Unlimited User Seats
**Best for:** Established dealerships who need end-to-end reporting and forecasting.
""")


# User Settings
with sidebar_tabs[2]:
    st.markdown("### ⚙️ Account Settings")
    st.markdown(f"**Current Status:** `{status}`")
    st.markdown(f"**Trial Expiry:** `{expiry_date.strftime('%Y-%m-%d')}`")
    st.markdown(f"**Total Listings Used:** `{usage_count}`")
    st.markdown(f"**Remaining Listings:** `{remaining_listings}`")

# ---------------------------------------------------------
# Main Tabs
# ---------------------------------------------------------
main_tabs = st.tabs(["🧾 Generate Listing", "📊 Analytics Dashboard", "📈 Inventory"])

# ----------------
# Generate Listing
# ----------------
with main_tabs[0]:
    if is_active and remaining_listings > 0:
        st.markdown("### 🧾 Generate a New Listing")

        with st.form("listing_form"):
            col1, col2 = st.columns(2)

            with col1:
                make = st.text_input("Car Make", "BMW")
                model = st.text_input("Model", "X5 M Sport")
                year = st.text_input("Year", "2021")
                mileage = st.text_input("Mileage", "28,000 miles")
                color = st.text_input("Color", "Black")
                car_image = st.file_uploader("Upload Car Image (optional)", type=["png","jpg","jpeg"])

            with col2:
                fuel = st.selectbox("Fuel Type", ["Petrol", "Diesel", "Hybrid", "Electric"])
                transmission = st.selectbox("Transmission", ["Automatic", "Manual"])
                price = st.text_input("Price", "£45,995")
                features = st.text_area("Key Features", "Panoramic roof, heated seats, M Sport package")
                notes = st.text_area("Dealer Notes (optional)", "Full service history, finance available")

            submitted = st.form_submit_button("✨ Generate Listing")

        if submitted:
            if not check_listing_limit(user_email):
                st.warning("⚠️ You have reached your free trial listing limit. Upgrade to continue.")
            else:
                try:
                    client = OpenAI(api_key=api_key)
                    prompt = f"""
Write a 120–150 word engaging car listing:
{year} {make} {model}, {mileage}, {color}, {fuel}, {transmission}, {price}.
Features: {features}. Dealer Notes: {notes}.
Include emojis and SEO-rich phrasing.
"""

                    with st.spinner("🤖 Generating your listing..."):
                        response = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {"role":"system","content":"You are a top-tier automotive copywriter."},
                                {"role":"user","content":prompt}
                            ],
                            temperature=0.7
                        )

                    listing_text = ""
                    if response and getattr(response, "choices", None):
                        listing_text = response.choices[0].message.content.strip()
                        st.success("✅ Listing generated successfully!")
                        st.markdown(f"**Generated Listing:**\n\n{listing_text}")
                        st.download_button("⬇ Download Listing", listing_text, file_name="listing.txt")

                    image_link = None
                    if car_image:
                        image_link = upload_image_to_drive(
                            car_image,
                            f"{make}_{model}_{datetime.utcnow().isoformat()}.png"
                        )
                        if not image_link:
                            st.warning("⚠️ Failed to upload image. Listing will be saved without image.")

                    inventory_data = {
                        "Email": user_email,
                        "Timestamp": datetime.utcnow().isoformat(),
                        "Make": make,
                        "Model": model,
                        "Year": year,
                        "Mileage": mileage,
                        "Color": color,
                        "Fuel": fuel,
                        "Transmission": transmission,
                        "Price": price,
                        "Features": features,
                        "Notes": notes,
                        "Listing": listing_text,
                        "Image_Link": image_link if image_link else ""
                    }

                    saved = append_to_google_sheet("Inventory", inventory_data)
                    if saved:
                        st.success("✅ Listing saved successfully to Google Sheets!")
                        increment_usage(user_email, 1)
                    else:
                        st.error("⚠️ Failed to save listing to Google Sheets.")

                except Exception as e:
                    st.error(f"⚠️ Unexpected error: {e}")

    else:
        st.warning("⚠️ Your trial has ended or listing limit reached. Please upgrade to continue.")

# ----------------
# Analytics Dashboard
# ----------------
# replace existing analytics tab block with this
from backend.plan_utils import has_feature

with main_tabs[1]:
    st.markdown("### 📊 Analytics Dashboard")

    # ensure session values
    st.session_state["user_email"] = st.session_state.get("user_email", user_email)
    st.session_state["plan"] = st.session_state.get("plan", profile.get("Plan", "free").lower())

    trial_is_active = status in ["active","new"] and remaining_days > 0

    # If trial active, give platinum
    if trial_is_active:
        st.success("🎉 You have full Platinum access for 30 days! All analytics unlocked.")
        show_analytics_dashboard(user_email, "platinum")
    else:
        plan = profile.get("Plan", "free").lower()
        if has_feature(plan, "analytics.platinum"):
            show_analytics_dashboard(user_email, plan)
        elif has_feature(plan, "analytics.pro"):
            show_analytics_dashboard(user_email, "pro")
        else:
            st.info("Upgrade to Pro or Platinum to view analytics. Start a 30-day trial to preview Platinum features.")


# ----------------
# Inventory Tab
# ----------------
# --- Inventory Tab ---
with main_tabs[2]:
    st.markdown("### 📈 Your Inventory")

    try:
        df_inventory = get_sheet_data("Inventory")

        # Handle empty or missing sheet
        if df_inventory is None or df_inventory.empty:
            st.info("No inventory has been added yet.")
            st.stop()

        # Ensure column names are normalised
        df_inventory.columns = [str(c).strip() for c in df_inventory.columns]

        # Fix case sensitivity: look for any form of "Email"
        possible_email_columns = ["Email", "email", "E-mail", "e-mail", "User", "user_email"]

        email_col = None
        for col in df_inventory.columns:
            if col.strip() in possible_email_columns:
                email_col = col
                break

        if not email_col:
            st.error("⚠️ Inventory sheet missing an 'Email' column. Please add one.")
            st.stop()

        # Filter inventory by user email
        df_inventory[email_col] = df_inventory[email_col].astype(str).str.lower()
        filtered = df_inventory[df_inventory[email_col] == user_email.lower()]

        if filtered.empty:
            st.info("You haven't added any listings yet.")
            st.stop()

        # Display listings
        for _, row in filtered.iterrows():
            st.subheader(f"{row.get('Year', '')} {row.get('Make', '')} {row.get('Model', '')}")

            # Show image if exists
            if row.get("Image_Link"):
                st.image(row["Image_Link"], width=300)

            # Show car details table
            details = {
                "Mileage": row.get("Mileage", "-"),
                "Color": row.get("Color", "-"),
                "Fuel": row.get("Fuel", "-"),
                "Transmission": row.get("Transmission", "-"),
                "Price": row.get("Price", "-"),
                "Features": row.get("Features", "-"),
                "Notes": row.get("Notes", "-"),
            }
            st.table(pd.DataFrame(details.items(), columns=["Attribute", "Value"]))

            st.markdown("#### Listing Description")
            st.write(row.get("Listing", "No description found."))

            st.markdown("---")

    except Exception as e:
        st.error(f"⚠️ Could not load inventory: {e}")


# ---------------------------------------------------------
# Footer
# ---------------------------------------------------------
st.markdown(
    '<div class="footer">© 2025 DealerCommand AI — Powered by FizMay Group</div>',
    unsafe_allow_html=True
)
