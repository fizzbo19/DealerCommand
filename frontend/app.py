# frontend/app.py
import sys, os, io, json
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
import plotly.express as px
from openai import OpenAI

# ---------------------------------------------------------
# PATH SETUP
# ---------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.extend([BASE_DIR, BACKEND_DIR])

# ---------------------------------------------------------
# LOCAL IMPORTS
# ---------------------------------------------------------
from backend.trial_manager import (
    get_dealership_status,
    check_listing_limit,
    increment_usage,
    can_user_login
)
from backend.sheet_utils import append_to_google_sheet, get_sheet_data, get_inventory_for_user
from backend.plan_utils import has_feature
from backend.stripe_utils import create_checkout_session
from backend.analytics import analytics_dashboard
from backend.platinum_manager import (
    is_platinum,
    can_add_listing,
    get_platinum_dashboard,
    increment_platinum_usage,
    get_platinum_remaining_listings,
    generate_ai_video_script,
    competitor_monitoring,
    generate_weekly_content_calendar
)

# ---------------------------------------------------------
# GOOGLE DRIVE SETUP
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
        st.warning("⚠️ Google Drive upload unavailable.")
        return None
    try:
        raw = os.environ.get("GOOGLE_CREDENTIALS_JSON") or os.environ.get("GOOGLE_CREDENTIALS")
        if not raw:
            st.warning("⚠️ GOOGLE_CREDENTIALS not set in environment.")
            return None
        info = json.loads(raw)
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/drive"])
        service = build('drive', 'v3', credentials=creds)
        file_obj.seek(0)
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

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(page_title="DealerCommand AI | Smart Listings", layout="wide", page_icon="🚗")
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
LOGO_FILE = os.path.join(ASSETS_DIR, "dealercommand_logov1.png")
if os.path.exists(LOGO_FILE):
    st.sidebar.image(LOGO_FILE, width=160, caption="DealerCommand AI")
else:
    st.sidebar.markdown("**DealerCommand AI**")

st.markdown('<h2 style="text-align:center;">🚗 DealerCommand AI</h2>', unsafe_allow_html=True)
st.markdown('<div class="hero-sub">Create high-converting, SEO-optimised car listings in seconds with AI.</div>', unsafe_allow_html=True)

# ---------------------------------------------------------
# OPENAI API KEY
# ---------------------------------------------------------
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    st.error("⚠️ Missing OpenAI API key. Set `OPENAI_API_KEY` in environment.")
    st.stop()
client = OpenAI(api_key=api_key)

def openai_generate(prompt, model="gpt-4o-mini", temperature=0.7):
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role":"system","content":"You are a top-tier automotive copywriter."},
                      {"role":"user","content":prompt}],
            temperature=temperature
        )
        if resp and getattr(resp, "choices", None):
            return resp.choices[0].message.content.strip()
        return ""
    except Exception as e:
        st.error(f"⚠️ OpenAI API error: {e}")
        return ""

# ---------------------------------------------------------
# DEALERSHIP LOGIN
# ---------------------------------------------------------
user_email = st.text_input("📧 Dealership email", placeholder="e.g. sales@autohub.co.uk")
if not user_email:
    st.info("👋 Enter your dealership email above to start your 30-day free trial.")
    st.stop()

profile = get_dealership_status(user_email)
plan = profile.get("Plan", "free").lower()
status = profile.get("Trial_Status", "new")
usage_count = profile.get("Usage_Count", 0)
remaining_listings = profile.get("Remaining_Listings", 15)
is_active = status in ["active", "new"]

if "platinum_trial_start" not in st.session_state:
    st.session_state["platinum_trial_start"] = datetime.utcnow()
trial_days_left = max(0, 30 - (datetime.utcnow() - st.session_state["platinum_trial_start"]).days)
is_trial_active = trial_days_left > 0
current_plan = "platinum" if is_trial_active else st.session_state.get('user_plan', plan)

if not can_user_login(user_email, plan):
    st.error(f"🚫 Seat limit reached for {plan.capitalize()} plan. Please contact account admin or upgrade plan.")
    st.stop()

# ---------------------------------------------------------
# FIRST-TIME DEALER INFO
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
# SIDEBAR
# ---------------------------------------------------------
st.sidebar.markdown("### 💳 Upgrade Plans")
plans = {
    "Premium": ["Social Media Analytics (basic)", "AI Captions (5/day)", "Inventory Upload (20 cars max)"],
    "Pro": ["Everything in Premium", "Full Social Analytics", "Dealer Performance Score", "AI Video Script Generator", "Compare Cars Analytics", "Export to CSV/Sheets"],
    "Platinum": ["Everything in Pro", "Custom Charts", "Market Price Intelligence", "AI Appraisal", "Automated Sales Forecasting", "Branding Kit", "White-Label Portal", "Priority Support"]
}
selected_upgrade = st.sidebar.selectbox("Upgrade to:", list(plans.keys()))
st.sidebar.markdown("**Features:**")
for f in plans[selected_upgrade]:
    st.sidebar.markdown(f"- {f}")
if st.sidebar.button("Upgrade Plan"):
    st.session_state['user_plan'] = selected_upgrade.lower()
    st.sidebar.success(f"✅ Upgraded to {selected_upgrade} plan!")

st.sidebar.markdown("### 🎯 Trial Overview")
st.sidebar.markdown(f"**👤 Email:** `{user_email}`")
st.sidebar.markdown(f"**📊 Listings Used:** `{usage_count}` / 15")
st.sidebar.progress(int(min((usage_count / 15) * 100, 100)))
st.sidebar.markdown(f"**🟢 Status:** {'Trial Active' if is_trial_active else 'Trial Ended'}")
st.sidebar.markdown(f"**⏳ Trial Days Remaining:** `{trial_days_left}`" if is_trial_active else "")

# ---------------------------------------------------------
# MAIN TABS
# ---------------------------------------------------------
main_tabs = st.tabs(["🧾 Generate Listing", "📊 Analytics Dashboard", "📈 Inventory"])

# ----------------
# GENERATE LISTING
# ----------------
with main_tabs[0]:
    if is_active and (remaining_listings > 0 or current_plan=="platinum"):
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
            if not can_add_listing(user_email):
                st.warning("⚠️ Listing limit reached. Upgrade to Platinum for unlimited.")
            else:
                prompt = f"""
Write a 120–150 word engaging car listing:
{year} {make} {model}, {mileage}, {color}, {fuel}, {transmission}, {price}.
Features: {features}. Dealer Notes: {notes}.
Include emojis and SEO-rich phrasing.
"""
                with st.spinner("🤖 Generating listing..."):
                    listing_text = openai_generate(prompt)
                st.success("✅ Listing generated!")
                st.text_area("Generated Listing", listing_text, height=250)
                st.download_button("⬇ Download Listing", listing_text, file_name=f"{make}_{model}_listing.txt")
                image_link = upload_image_to_drive(car_image, f"{make}_{model}_{datetime.utcnow().isoformat()}.png") if car_image else ""
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
                    "Image_Link": image_link or ""
                }
                if append_to_google_sheet("Inventory", inventory_data):
                    st.success("✅ Listing saved!")
                    increment_platinum_usage(user_email, 1)
                else:
                    st.error("⚠️ Failed to save listing.")
    else:
        st.warning("⚠️ Trial ended or listing limit reached. Upgrade to continue.")

# ----------------
# ANALYTICS DASHBOARD
# ----------------
with main_tabs[1]:
    st.markdown("### 📊 Analytics Dashboard")
    show_demo_charts = st.checkbox("🎨 Show Demo Charts", value=True)
    if current_plan=="platinum":
        dashboard = get_platinum_dashboard(user_email)
        st.markdown(f"**👤 Email:** {dashboard['Profile']['Email']}")
        st.markdown(f"**Plan:** {dashboard['Profile']['Plan']}")
        st.markdown(f"**Inventory Count:** {dashboard['Inventory_Count']}")
        st.markdown(f"**Remaining Listings:** {dashboard['Remaining_Listings']}")
        # Top recommendations
        top_df = pd.DataFrame(dashboard.get("Top_Recommendations", []))
        if show_demo_charts or top_df.empty:
            fig_demo = px.bar(x=["Car A","Car B","Car C"], y=[5,3,2], text=[5,3,2], title="Top Recommendations Demo")
            st.plotly_chart(fig_demo, use_container_width=True)
        else:
            st.dataframe(top_df)

# ----------------
# INVENTORY TAB
# ----------------
with main_tabs[2]:
    st.markdown("### 📈 Your Inventory")
    try:
        df_inventory = get_sheet_data("Inventory")
        if df_inventory is None or df_inventory.empty:
            st.info("No inventory added yet.")
            st.stop()
        df_inventory.columns = [str(c).strip() for c in df_inventory.columns]
        email_col = next((c for c in df_inventory.columns if c.lower()=="email"), None)
        if not email_col:
            st.error("⚠️ Inventory sheet missing an 'Email' column.")
            st.stop()
        df_inventory[email_col] = df_inventory[email_col].astype(str).str.lower()
        filtered = df_inventory[df_inventory[email_col]==user_email.lower()]
        if filtered.empty:
            st.info("No listings for your account yet.")
            st.stop()
        for idx, row in filtered.iterrows():
            st.subheader(f"{row.get('Year','')} {row.get('Make','')} {row.get('Model','')}")
            if row.get("Image_Link"):
                st.image(row["Image_Link"], width=300)
            details = {k: row.get(k,"-") for k in ["Mileage","Color","Fuel","Transmission","Price","Features","Notes"]}
            st.table(pd.DataFrame(details.items(), columns=["Attribute","Value"]))
            st.markdown("#### Listing Description")
            st.write(row.get("Listing","No description found."))
            st.markdown("---")
    except Exception as e:
        st.error(f"⚠️ Error loading inventory: {e}")

