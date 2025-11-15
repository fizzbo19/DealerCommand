# frontend/app.py
import sys, os, io, json
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
import plotly.express as px
from openai import OpenAI
import random

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

import random  # Add this at the top of your app.py if not already imported

# ----------------
# ANALYTICS DASHBOARD (8 Dynamic Demo Dashboards)
# ----------------
with main_tabs[1]:
    st.markdown("### 📊 Analytics Dashboard")
    show_demo_charts = st.checkbox("🎨 Show Demo Charts", value=True)

    if current_plan == "platinum":
        st.markdown("### 🔹 Demo Dashboards for Platinum Users")

        for i in range(1, 9):  # 8 demo dashboards
            st.markdown(f"## Demo Dashboard {i}")

            # ----------------
            # Top Recommendations
            # ----------------
            demo_top_recs = pd.DataFrame([
                {"Year":"2021","Make":"BMW","Model":"X5 M Sport","Score":random.randint(80,90)},
                {"Year":"2022","Make":"Audi","Model":"Q7","Score":random.randint(75,85)},
                {"Year":"2020","Make":"Mercedes","Model":"GLE","Score":random.randint(70,80)}
            ])
            fig_top = px.bar(
                demo_top_recs,
                x="Model",
                y="Score",
                text="Score",
                color="Make",
                title=f"Top Recommendations Demo {i}"
            )
            st.plotly_chart(fig_top, use_container_width=True)

            # ----------------
            # Social Media Insights
            # ----------------
            demo_social = pd.DataFrame({
                "Week":["Week 1","Week 2","Week 3","Week 4"],
                "Instagram Likes":[random.randint(100,150) for _ in range(4)],
                "Facebook Likes":[random.randint(70,120) for _ in range(4)],
                "Leads":[random.randint(8,15) for _ in range(4)]
            })
            fig_social = px.line(
                demo_social,
                x="Week",
                y=["Instagram Likes","Facebook Likes","Leads"],
                markers=True,
                title=f"Social Media Performance Demo {i}"
            )
            st.plotly_chart(fig_social, use_container_width=True)

            # ----------------
            # Inventory Summary
            # ----------------
            demo_inventory_summary = pd.DataFrame({
                "Make":["BMW","Audi","Mercedes","Tesla"],
                "Count":[random.randint(3,7) for _ in range(4)],
                "Average Price":[random.randint(45000,60000) for _ in range(4)]
            })
            st.markdown("**Inventory Summary**")
            st.table(demo_inventory_summary)

            # ----------------
            # AI Video Script Generator Demo
            # ----------------
            st.markdown("### 🎬 AI Video Script Generator")
            sample_listing = demo_top_recs.iloc[0]
            demo_script = f"""
Introducing the {sample_listing['Year']} {sample_listing['Make']} {sample_listing['Model']}!
Luxury and performance combined. ✅ High-quality interiors, sleek design, and powerful engine.
Perfect for family trips or city driving. 🚗💨
Contact us now to book a test drive!
"""
            st.text_area("🎬 Demo Video Script", demo_script, height=150)
            st.download_button(
                "⬇ Download Demo Script",
                demo_script,
                file_name=f"{sample_listing['Make']}_{sample_listing['Model']}_demo_script.txt"
            )

            # ----------------
            # Competitor Monitoring Demo
            # ----------------
            st.markdown("### 🏁 Competitor Monitoring (Demo)")
            demo_competitors = pd.DataFrame([
                {"Competitor":"AutoHub","Make":"BMW","Model":"X5","Price":random.randint(47000,50000),"Location":"London"},
                {"Competitor":"CarMax","Make":"Audi","Model":"Q7","Price":random.randint(46000,49000),"Location":"Manchester"},
                {"Competitor":"MotorWorld","Make":"Mercedes","Model":"GLE","Price":random.randint(53000,56000),"Location":"Birmingham"}
            ])
            st.dataframe(demo_competitors)
            st.download_button(
                "⬇ Download Competitor Data",
                demo_competitors.to_csv(index=False),
                file_name=f"competitor_demo_data_{i}.csv"
            )

            # ----------------
            # Weekly Content Calendar Demo
            # ----------------
            st.markdown("### 📅 Weekly Content Calendar (Demo)")
            demo_calendar = pd.DataFrame({
                "Day":["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
                "Content":[
                    random.choice(["Listing Highlight","Social Post","Video Script","Tips & Tricks","Wrap Up"]) for _ in range(7)
                ],
                "Platform":[random.choice(["Instagram","Facebook","LinkedIn"]) for _ in range(7)]
            })
            st.dataframe(demo_calendar)
            st.download_button(
                "⬇ Download Weekly Content Calendar",
                demo_calendar.to_csv(index=False),
                file_name=f"weekly_content_calendar_demo_{i}.csv"
            )

            st.markdown("---")


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

