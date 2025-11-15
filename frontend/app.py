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

# ----------------
# ANALYTICS DASHBOARD (8 Unique Demo Dashboards)
# ----------------
with main_tabs[1]:
    st.markdown("### 📊 Analytics Dashboard")
    show_demo_charts = st.checkbox("🎨 Show Demo Charts", value=True)

    if current_plan == "platinum":
        st.markdown("### 🔹 Demo Dashboards for Platinum Users")

        # Sample demo images (used for all dashboards)
        demo_car_images = [
            "https://source.unsplash.com/400x300/?bmw,car",
            "https://source.unsplash.com/400x300/?audi,car",
            "https://source.unsplash.com/400x300/?mercedes,car",
            "https://source.unsplash.com/400x300/?tesla,car",
            "https://source.unsplash.com/400x300/?jaguar,car"
        ]

        # ----- Demo Data for 8 Dashboards -----
        demo_data = [
            {
                "top_recs": [
                    {"Year":"2021","Make":"BMW","Model":"X5 M Sport","Score":88},
                    {"Year":"2022","Make":"Audi","Model":"Q7","Score":82},
                    {"Year":"2020","Make":"Mercedes","Model":"GLE","Score":79}
                ],
                "social": {
                    "Instagram Likes":[120,135,140,150],
                    "Facebook Likes":[100,110,115,120],
                    "Twitter Retweets":[30,35,32,40],
                    "Website Clicks":[60,70,65,80],
                    "Leads":[10,12,14,13]
                },
                "inventory": [
                    {"Make":"BMW","Count":5,"Average Price":54000},
                    {"Make":"Audi","Count":4,"Average Price":52000},
                    {"Make":"Mercedes","Count":3,"Average Price":58000},
                    {"Make":"Tesla","Count":2,"Average Price":60000}
                ]
            },
            # Dashboard 2
            {
                "top_recs": [
                    {"Year":"2022","Make":"Audi","Model":"Q8","Score":87},
                    {"Year":"2021","Make":"BMW","Model":"X6","Score":84},
                    {"Year":"2020","Make":"Mercedes","Model":"GLC","Score":76}
                ],
                "social": {
                    "Instagram Likes":[130,140,125,135],
                    "Facebook Likes":[90,105,100,110],
                    "Twitter Retweets":[25,30,28,32],
                    "Website Clicks":[55,65,60,70],
                    "Leads":[9,11,12,10]
                },
                "inventory": [
                    {"Make":"BMW","Count":3,"Average Price":53000},
                    {"Make":"Audi","Count":5,"Average Price":54000},
                    {"Make":"Mercedes","Count":4,"Average Price":57000},
                    {"Make":"Tesla","Count":3,"Average Price":61000}
                ]
            },
            # Dashboard 3
            {
                "top_recs": [
                    {"Year":"2020","Make":"Mercedes","Model":"GLE Coupe","Score":85},
                    {"Year":"2021","Make":"BMW","Model":"X3 M","Score":80},
                    {"Year":"2022","Make":"Audi","Model":"Q5","Score":78}
                ],
                "social": {
                    "Instagram Likes":[115,120,125,130],
                    "Facebook Likes":[85,95,100,105],
                    "Twitter Retweets":[20,25,22,28],
                    "Website Clicks":[50,60,55,65],
                    "Leads":[8,9,10,11]
                },
                "inventory": [
                    {"Make":"BMW","Count":4,"Average Price":52000},
                    {"Make":"Audi","Count":3,"Average Price":50000},
                    {"Make":"Mercedes","Count":5,"Average Price":58000},
                    {"Make":"Tesla","Count":2,"Average Price":62000}
                ]
            },
            # Dashboard 4
            {
                "top_recs": [
                    {"Year":"2021","Make":"Tesla","Model":"Model X","Score":90},
                    {"Year":"2022","Make":"BMW","Model":"iX","Score":85},
                    {"Year":"2021","Make":"Audi","Model":"e-tron","Score":80}
                ],
                "social": {
                    "Instagram Likes":[150,160,155,165],
                    "Facebook Likes":[120,130,125,135],
                    "Twitter Retweets":[35,40,38,42],
                    "Website Clicks":[70,80,75,85],
                    "Leads":[12,14,13,15]
                },
                "inventory": [
                    {"Make":"BMW","Count":2,"Average Price":65000},
                    {"Make":"Audi","Count":3,"Average Price":62000},
                    {"Make":"Mercedes","Count":4,"Average Price":64000},
                    {"Make":"Tesla","Count":5,"Average Price":70000}
                ]
            },
            # Dashboard 5
            {
                "top_recs": [
                    {"Year":"2021","Make":"Jaguar","Model":"F-Pace","Score":82},
                    {"Year":"2022","Make":"Land Rover","Model":"Discovery","Score":85},
                    {"Year":"2020","Make":"BMW","Model":"X4","Score":78}
                ],
                "social": {
                    "Instagram Likes":[110,115,120,125],
                    "Facebook Likes":[95,100,105,110],
                    "Twitter Retweets":[18,22,20,25],
                    "Website Clicks":[50,55,52,60],
                    "Leads":[7,8,9,10]
                },
                "inventory": [
                    {"Make":"BMW","Count":3,"Average Price":51000},
                    {"Make":"Jaguar","Count":4,"Average Price":56000},
                    {"Make":"Land Rover","Count":3,"Average Price":59000},
                    {"Make":"Tesla","Count":2,"Average Price":68000}
                ]
            },
            # Dashboard 6
            {
                "top_recs": [
                    {"Year":"2022","Make":"Porsche","Model":"Cayenne","Score":88},
                    {"Year":"2021","Make":"Audi","Model":"Q8","Score":82},
                    {"Year":"2020","Make":"Mercedes","Model":"GLE","Score":79}
                ],
                "social": {
                    "Instagram Likes":[125,130,140,145],
                    "Facebook Likes":[105,110,115,120],
                    "Twitter Retweets":[28,30,32,35],
                    "Website Clicks":[65,70,68,75],
                    "Leads":[10,11,13,12]
                },
                "inventory": [
                    {"Make":"Porsche","Count":3,"Average Price":75000},
                    {"Make":"Audi","Count":5,"Average Price":54000},
                    {"Make":"Mercedes","Count":4,"Average Price":58000},
                    {"Make":"Tesla","Count":2,"Average Price":65000}
                ]
            },
            # Dashboard 7
            {
                "top_recs": [
                    {"Year":"2021","Make":"BMW","Model":"M3","Score":86},
                    {"Year":"2022","Make":"Audi","Model":"RS7","Score":84},
                    {"Year":"2020","Make":"Mercedes","Model":"C63 AMG","Score":81}
                ],
                "social": {
                    "Instagram Likes":[135,140,145,150],
                    "Facebook Likes":[120,125,130,135],
                    "Twitter Retweets":[30,32,34,36],
                    "Website Clicks":[70,75,72,78],
                    "Leads":[11,12,13,14]
                },
                "inventory": [
                    {"Make":"BMW","Count":5,"Average Price":60000},
                    {"Make":"Audi","Count":4,"Average Price":62000},
                    {"Make":"Mercedes","Count":3,"Average Price":63000},
                    {"Make":"Tesla","Count":2,"Average Price":67000}
                ]
            },
            # Dashboard 8
            {
                "top_recs": [
                    {"Year":"2022","Make":"Mercedes","Model":"S-Class","Score":92},
                    {"Year":"2021","Make":"BMW","Model":"7 Series","Score":88},
                    {"Year":"2022","Make":"Audi","Model":"A8","Score":85}
                ],
                "social": {
                    "Instagram Likes":[160,165,170,175],
                    "Facebook Likes":[140,145,150,155],
                    "Twitter Retweets":[40,42,45,48],
                    "Website Clicks":[80,85,82,90],
                    "Leads":[14,15,16,17]
                },
                "inventory": [
                    {"Make":"BMW","Count":4,"Average Price":85000},
                    {"Make":"Audi","Count":3,"Average Price":82000},
                    {"Make":"Mercedes","Count":5,"Average Price":88000},
                    {"Make":"Tesla","Count":2,"Average Price":90000}
                ]
            }
        ]

        # ----------------
        # Loop through each demo dashboard
        # ----------------
        for i, data in enumerate(demo_data, start=1):
            st.markdown(f"## Demo Dashboard {i}")

            # ---- Top Recommendations ----
            demo_top_recs = pd.DataFrame(data["top_recs"])
            fig_top = px.bar(
                demo_top_recs,
                x="Model",
                y="Score",
                text="Score",
                color="Make",
                title=f"Top Recommendations Demo {i}"
            )
            st.plotly_chart(fig_top, use_container_width=True)

            # Sample images for top recommendations
            st.markdown("**🚗 Sample Car Images**")
            cols = st.columns(3)
            for idx, row in demo_top_recs.iterrows():
                img_url = random.choice(demo_car_images)
                col = cols[idx % 3]
                col.image(img_url, caption=f"{row['Year']} {row['Make']} {row['Model']}", use_container_width=True)

            # ---- Social & Engagement Charts ----
            demo_social = pd.DataFrame(data["social"])
            demo_social["Week"] = ["Week 1","Week 2","Week 3","Week 4"]

            fig_social_line = px.line(
                demo_social,
                x="Week",
                y=["Instagram Likes","Facebook Likes","Twitter Retweets"],
                markers=True,
                title=f"📈 Social Engagement Demo {i}"
            )
            st.plotly_chart(fig_social_line, use_container_width=True)

            fig_clicks = px.bar(
                demo_social,
                x="Week",
                y=["Website Clicks","Leads"],
                barmode="group",
                text_auto=True,
                title=f"🖱 Website Clicks & Leads Demo {i}"
            )
            st.plotly_chart(fig_clicks, use_container_width=True)

            last_week = demo_social.iloc[-1]
            fig_pie = px.pie(
                names=["Instagram Likes","Facebook Likes","Twitter Retweets"],
                values=[last_week["Instagram Likes"], last_week["Facebook Likes"], last_week["Twitter Retweets"]],
                title=f"📊 Last Week Platform Engagement Demo {i}"
            )
            st.plotly_chart(fig_pie, use_container_width=True)

            # ---- Inventory Summary ----
            demo_inventory_summary = pd.DataFrame(data["inventory"])
            st.markdown("**Inventory Summary**")
            st.table(demo_inventory_summary)

            # Inventory Images
            st.markdown("**🚘 Inventory Images**")
            inv_cols = st.columns(len(demo_inventory_summary))
            for idx, row in demo_inventory_summary.iterrows():
                col = inv_cols[idx % len(inv_cols)]
                img_url = random.choice(demo_car_images)
                col.image(img_url, caption=f"{row['Make']} - £{row['Average Price']}", use_container_width=True)

            # ---- AI Video Script Generator ----
            st.markdown("### 🎬 AI Video Script Generator")
            sample_listing = demo_top_recs.iloc[0]
            demo_script = f"""
Introducing the {sample_listing['Year']} {sample_listing['Make']} {sample_listing['Model']}!
Luxury and performance combined. ✅ High-quality interiors, sleek design, and powerful engine.
Perfect for family trips or city driving. 🚗💨
Contact us now to book a test drive!
"""
            st.text_area(f"🎬 Demo Video Script {i}", demo_script, height=150, key=f"demo_script_{i}")
            st.download_button(
                f"⬇ Download Demo Script {i}",
                demo_script,
                file_name=f"{sample_listing['Make']}_{sample_listing['Model']}_demo_script_{i}.txt",
                key=f"download_demo_script_{i}"
            )

            # ---- Competitor Monitoring ----
            st.markdown("### 🏁 Competitor Monitoring (Demo)")
            demo_competitors = pd.DataFrame([
                {"Competitor":"AutoHub","Make":"BMW","Model":"X5","Price":random.randint(47000,50000),"Location":"London"},
                {"Competitor":"CarMax","Make":"Audi","Model":"Q7","Price":random.randint(46000,49000),"Location":"Manchester"},
                {"Competitor":"MotorWorld","Make":"Mercedes","Model":"GLE","Price":random.randint(53000,56000),"Location":"Birmingham"}
            ])
            st.dataframe(demo_competitors)
            st.download_button(
                f"⬇ Download Competitor Data {i}",
                demo_competitors.to_csv(index=False),
                file_name=f"competitor_demo_data_{i}.csv",
                key=f"download_competitor_{i}"
            )

            # ---- Weekly Content Calendar ----
            st.markdown("### 📅 Weekly Content Calendar (Demo)")
            demo_calendar = pd.DataFrame({
                "Day":["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
                "Content":[random.choice(["Listing Highlight","Social Post","Video Script","Tips & Tricks","Wrap Up"]) for _ in range(7)],
                "Platform":[random.choice(["Instagram","Facebook","LinkedIn"]) for _ in range(7)]
            })
            st.dataframe(demo_calendar)
            st.download_button(
                f"⬇ Download Weekly Content Calendar {i}",
                demo_calendar.to_csv(index=False),
                file_name=f"weekly_content_calendar_demo_{i}.csv",
                key=f"download_calendar_{i}"
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

