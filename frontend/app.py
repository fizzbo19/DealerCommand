# frontend/app.py
import sys, os, io, json
from datetime import datetime
import streamlit as st
import pandas as pd
from openai import OpenAI

# ----------------------
# Local imports
# ----------------------
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.trial_manager import get_dealership_status, check_listing_limit, increment_usage
from backend.sheet_utils import append_to_google_sheet, get_sheet_data
from backend.stripe_utils import create_checkout_session

# ----------------------
# Google Drive upload (graceful)
# ----------------------
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
        uploaded = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        file_id = uploaded.get("id")
        service.permissions().create(fileId=file_id, body={"role": "reader", "type": "anyone"}).execute()
        return f"https://drive.google.com/uc?id={file_id}"
    except Exception as e:
        print(f"⚠️ Failed to upload image: {e}")
        return None

# ----------------------
# PAGE CONFIG & UI
# ----------------------
st.set_page_config(page_title="DealerCommand AI | Smart Listings", layout="wide", page_icon="🚗")
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
LOGO_FILE = os.path.join(ASSETS_DIR, "dealercommand_logov1.png")
if os.path.exists(LOGO_FILE):
    st.sidebar.image(LOGO_FILE, width=160, caption="DealerCommand AI")
else:
    st.sidebar.markdown("**DealerCommand AI**")

st.markdown('<h2 style="text-align:center;">🚗 DealerCommand AI</h2>', unsafe_allow_html=True)
st.markdown('<div class="hero-sub">Create high-converting, SEO-optimised car listings in seconds with AI.</div>', unsafe_allow_html=True)

# ----------------------
# API KEY CHECK
# ----------------------
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    st.error("⚠️ Missing OpenAI API key. Set `OPENAI_API_KEY` in environment.")
    st.stop()

# ----------------------
# DEALER LOGIN / EMAIL INPUT
# ----------------------
user_email = st.text_input("📧 Dealership email", placeholder="e.g. sales@autohub.co.uk")
if not user_email:
    st.info("👋 Enter your dealership email above to start your 30-day free trial.")
    st.stop()

# ----------------------
# FETCH PROFILE & TRIAL STATUS
# ----------------------
profile = get_dealership_status(user_email)
status = profile["Trial_Status"]
expiry_date = profile["Trial_Expiry"]
usage_count = profile["Usage_Count"]
remaining_listings = profile["Remaining_Listings"]
is_active = status in ["active", "new"]

# ----------------------
# FIRST-TIME DEALERSHIP INFO
# ----------------------
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

# ----------------------
# SIDEBAR TABS
# ----------------------
sidebar_tabs = st.sidebar.tabs(["🎯 Trial Overview", "💳 Upgrade Plans", "⚙️ User Settings"])

# --- Trial Overview ---
with sidebar_tabs[0]:
    st.markdown("### 🎯 Your DealerCommand Trial")
    st.markdown(f"**👤 Email:** `{user_email}`")
    st.markdown(f"**📊 Listings Used:** `{usage_count}` / 15")
    st.progress(int(min((usage_count / 15) * 100, 100)))
    if is_active:
        remaining_days = max((expiry_date - datetime.utcnow()).days, 0)
        st.markdown(f"**🟢 Status:** Active Trial")
        st.markdown(f"**⏳ Days Remaining:** `{remaining_days}` days")
        st.markdown(f"**📅 Ends On:** `{expiry_date.strftime('%B %d, %Y')}`")
        st.markdown(f"**📌 Remaining Listings:** `{remaining_listings}`")
    else:
        st.error("🚫 Your trial has expired. Upgrade to continue using DealerCommand.")

# --- Upgrade Plans ---
with sidebar_tabs[1]:
    st.markdown("### 💳 Upgrade Your Plan")
    st.caption("Select a plan to unlock more listings, analytics, and support.")
    plans = [
        ("Starter Plan – £29/month", "starter"),
        ("Pro Plan – £59/month", "pro"),
        ("Premium – £29.99/month", "premium"),
        ("Pro Plus – £59.99/month", "pro_plus")
    ]
    for title, plan_key in plans:
        st.markdown(f"#### {title}")
        checkout_url = create_checkout_session(user_email, plan=plan_key)
        st.markdown(f"[Upgrade to {title}]({checkout_url})", unsafe_allow_html=True)
        st.markdown("---")

# --- User Settings ---
with sidebar_tabs[2]:
    st.markdown("### ⚙️ Account Settings")
    st.markdown(f"**Current Status:** `{status}`")
    st.markdown(f"**Trial Expiry:** `{expiry_date.strftime('%Y-%m-%d')}`")
    st.markdown(f"**Total Listings Used:** `{usage_count}`")
    st.markdown(f"**Remaining Listings:** `{remaining_listings}`")

# ----------------------
# MAIN TABS
# ----------------------
main_tabs = st.tabs(["🧾 Generate Listing", "📊 Analytics Dashboard", "📈 Inventory"])

# --- Generate Listing ---
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
                    # ------------------------
                    # 1️⃣ OpenAI Listing Generation
                    # ------------------------
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

                    # Safe handling of AI response
                    if response is None or not getattr(response, "choices", None):
                        st.error("⚠️ OpenAI API returned no response. Please try again.")
                        listing_text = ""
                    else:
                        listing_text = response.choices[0].message.content.strip()
                        st.success("✅ Listing generated successfully!")
                        st.markdown(f"**Generated Listing:**\n\n{listing_text}")
                        st.download_button("⬇ Download Listing", listing_text, file_name="listing.txt")

                    # ------------------------
                    # 2️⃣ Upload Image (Optional)
                    # ------------------------
                    image_link = None
                    if car_image:
                        image_link = upload_image_to_drive(
                            car_image,
                            f"{make}_{model}_{datetime.utcnow().isoformat()}.png"
                        )
                        if not image_link:
                            st.warning("⚠️ Failed to upload image. Listing will be saved without image.")

                    # ------------------------
                    # 3️⃣ Save Listing to Google Sheets
                    # ------------------------
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


# --- Analytics Dashboard ---
with main_tabs[1]:
    st.markdown("### 📊 Analytics Dashboard")
    st.info("Upgrade to view engagement analytics, conversion rates, and SEO performance.")

# --- Inventory Tab ---
with main_tabs[2]:
    st.markdown("### 📈 Your Inventory")
    try:
        df_inventory = get_sheet_data("Inventory")
        user_inventory = df_inventory[df_inventory["Email"].str.lower() == user_email.lower()]
        if not user_inventory.empty:
            for _, row in user_inventory.iterrows():
                st.markdown(f"**{row['Year']} {row['Make']} {row['Model']}**")
                if row.get("Image_Link"):
                    st.image(row["Image_Link"], width=300)
                st.write(row[["Mileage","Color","Fuel","Transmission","Price","Features","Notes","Listing"]])
                st.markdown("---")
        else:
            st.info("No listings yet.")
    except Exception as e:
        st.error(f"⚠️ Could not load inventory: {e}")

# ----------------------
# FOOTER
# ----------------------
st.markdown(
    '<div class="footer">© 2025 DealerCommand AI — Powered by FizMay Group</div>',
    unsafe_allow_html=True
)
