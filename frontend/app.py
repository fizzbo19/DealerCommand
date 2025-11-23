import sys, os, io, json
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
import plotly.express as px
from openai import OpenAI
import random
import io
import zipfile

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
# DEALERSHIP LOGIN (Updated for persistent trial tracking)
# ---------------------------------------------------------
user_email = st.text_input("📧 Dealership email", placeholder="e.g. sales@autohub.co.uk")
if not user_email:
    st.info("👋 Enter your dealership email above to start your 30-day free trial.")
    st.stop()

# Use the full status from trial_manager
profile = get_dealership_status(user_email)
plan = profile.get("Plan", "free").lower()
status = profile.get("Trial_Status", "new")
usage_count = profile.get("Usage_Count", 0)
remaining_listings = profile.get("Remaining_Listings", 15)
is_active = status in ["active", "new"]

# --- FIX: Calculate trial days based on persistent Expiry Date from backend ---

TRIAL_EXPIRY_DATE = profile.get("Trial_Expiry") # This is a datetime object from trial_manager

if TRIAL_EXPIRY_DATE:
    time_remaining = TRIAL_EXPIRY_DATE - datetime.utcnow()
    trial_days_left = max(0, time_remaining.days)
    is_trial_active = time_remaining.total_seconds() > 0
else:
    # Fallback if Trial_Expiry is somehow missing
    trial_days_left = 30
    is_trial_active = True

# current_plan logic simplified to rely on profile status
current_plan = plan if not is_trial_active else 'platinum' # Assuming active trial defaults to platinum features

# --- END FIX ---

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
            # save_dealership_profile handles UPSERT on Dealership_Profiles tab
            from backend.sheet_utils import save_dealership_profile
            save_dealership_profile(user_email, {
                "Name": dealer_name,
                "Phone": dealer_phone,
                "Location": dealer_location,
                # Trial_Status and Plan are handled by trial_manager
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
        
        # Form definition moved inside the 'if' block to fix indentation issues
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
                    # This calls decrement_listing_count which updates the usage in User_Activity tab
                    increment_platinum_usage(user_email, 1) 
                else:
                    st.error("⚠️ Failed to save listing.")
    else:
        st.warning("⚠️ Trial ended or listing limit reached. Upgrade to continue.")

# ----------------
# ANALYTICS DASHBOARD (8 Unique Demo Dashboards + Extras)
# ----------------



with main_tabs[1]:
    st.markdown("### 📊 Analytics Dashboard")
    show_demo_charts = st.checkbox("🎨 Show Demo Dashboards", value=True, key="show_demo_charts")

    # --- Filter Widgets ---
    all_makes = ["All", "BMW", "Audi", "Mercedes", "Tesla", "Jaguar", "Land Rover", "Porsche"]
    all_models = ["All", "X5 M Sport", "Q7", "GLE", "Q8", "X6", "GLC", "GLE Coupe", "X3 M", "Q5", "Model X", "iX", "e-tron", "F-Pace", "Discovery", "X4", "Cayenne", "M3", "RS7", "C63 AMG", "S-Class", "7 Series", "A8"]

    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        selected_make = st.selectbox("Filter by Make", all_makes)
    with filter_col2:
        selected_model = st.selectbox("Filter by Model", all_models)

    # --- Dealer CSV Upload for Custom Dashboard ---
    st.markdown("### 🔁 Upload your dealer inventory CSV")
    dealer_csv = st.file_uploader(
        "Upload CSV (optional) — generates a custom dashboard",
        type=["csv"],
        key="dealer_inventory_upload"
    )

    def chart_ai_suggestion(chart_name, sample_data):
        prompt = f"""
You are an automotive sales analyst. Here is some inventory data sample:
{sample_data}
Provide 1 concise insight specifically about {chart_name} and 1 actionable suggestion to improve performance.
"""
        return openai_generate(prompt)

    if dealer_csv is not None:
        try:
            dealer_df = pd.read_csv(dealer_csv)
            st.success("✅ Dealer inventory loaded. Generating custom dashboard...")

            # Clean numeric columns
            if "Price" in dealer_df.columns:
                dealer_df["Price_numeric"] = pd.to_numeric(dealer_df["Price"].replace('£','', regex=True).replace(',','', regex=True), errors='coerce')
            else:
                dealer_df["Price_numeric"] = 0
            if "Mileage" in dealer_df.columns:
                dealer_df["Mileage_numeric"] = pd.to_numeric(dealer_df["Mileage"].str.replace(" miles","").str.replace(",",""), errors="coerce")
            else:
                dealer_df["Mileage_numeric"] = 0
            if "Timestamp" in dealer_df.columns:
                dealer_df["Timestamp"] = pd.to_datetime(dealer_df["Timestamp"], errors="coerce")
                dealer_df["Date"] = dealer_df["Timestamp"].dt.date

            # --- Summary Metrics ---
            st.markdown("#### Dealer Inventory Summary")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Cars", len(dealer_df))
            col2.metric("Average Price", f"£{int(dealer_df['Price_numeric'].mean()):,}" if len(dealer_df)>0 else "£0")
            col3.metric("Average Mileage", f"{int(dealer_df['Mileage_numeric'].mean()):,} miles" if len(dealer_df)>0 else "-")
            if "Make" in dealer_df.columns and len(dealer_df)>0:
                col4.metric("Most Common Make", dealer_df['Make'].mode()[0])
            else:
                col4.metric("Most Common Make", "-")

            # --- Charts ---
            if "Price_numeric" in dealer_df.columns:
                st.markdown("#### 🏷 Price Distribution")
                fig_price = px.histogram(dealer_df, x="Price_numeric", nbins=20, title="Price Distribution")
                st.plotly_chart(fig_price, use_container_width=True)
                st.info(f"💡 AI Insight: {chart_ai_suggestion('Price Distribution', dealer_df.head(10).to_dict(orient='records'))}")

            if "Mileage_numeric" in dealer_df.columns and "Price_numeric" in dealer_df.columns:
                st.markdown("#### 🚗 Mileage vs Price")
                fig_mileage = px.scatter(dealer_df, x="Mileage_numeric", y="Price_numeric",
                                         color="Make" if "Make" in dealer_df.columns else None,
                                         hover_data=["Model","Year"] if "Model" in dealer_df.columns and "Year" in dealer_df.columns else None,
                                         title="Mileage vs Price")
                st.plotly_chart(fig_mileage, use_container_width=True)
                st.info(f"💡 AI Insight: {chart_ai_suggestion('Mileage vs Price', dealer_df.head(10).to_dict(orient='records'))}")

            if "Date" in dealer_df.columns:
                st.markdown("#### ⏱ Listings Over Time")
                trends = dealer_df.groupby("Date").size().reset_index(name="Listings")
                fig_trends = px.line(trends, x="Date", y="Listings", title="Listings Added Over Time", markers=True)
                st.plotly_chart(fig_trends, use_container_width=True)
                st.info(f"💡 AI Insight: {chart_ai_suggestion('Listings Over Time', dealer_df.head(10).to_dict(orient='records'))}")

            if "Make" in dealer_df.columns:
                st.markdown("#### 🏆 Top Makes")
                make_counts = dealer_df['Make'].value_counts().reset_index()
                make_counts.columns = ["Make","Count"]
                fig_make = px.pie(make_counts, names="Make", values="Count", title="Inventory by Make")
                st.plotly_chart(fig_make, use_container_width=True)
                st.info(f"💡 AI Insight: {chart_ai_suggestion('Top Makes Pie Chart', dealer_df.head(10).to_dict(orient='records'))}")

        except Exception as e:
            st.error(f"⚠️ Error loading dealer CSV: {e}")

    # --- 5 Demo Dashboards at Bottom ---
    if show_demo_charts:
        st.markdown("---")
        st.markdown("### 🎨 Demo Dashboards for Reference")
        demo_data = demo_data[:5]  # keep 5 demo dashboards

        def get_car_image_url(make):
            text = str(make).split()[0].upper() + "%20CAR"
            return f"https://placehold.co/600x400/31363F/F0F7FF?text={text}"

        for i, data in enumerate(demo_data, start=1):
            df_top = pd.DataFrame(data["top_recs"])
            if selected_make != "All" and selected_make not in df_top["Make"].values:
                continue
            if selected_model != "All" and selected_model not in df_top["Model"].values:
                continue

            st.markdown(f"## Demo Dashboard {i}")

            # --- Top Recommendations ---
            fig_top = px.bar(df_top, x="Model", y="Score", text="Score", color="Make", title=f"Top Recommendations Demo {i}")
            st.plotly_chart(fig_top, use_container_width=True)
            st.info(f"💡 AI Insight: {chart_ai_suggestion(f'Demo Top Recommendations {i}', df_top.head(3).to_dict(orient='records'))}")

            # Sample Images
            st.markdown("**🚗 Sample Car Images**")
            cols = st.columns(3)
            for idx, row in df_top.iterrows():
                img_url = get_car_image_url(row["Make"])
                col = cols[idx % 3]
                col.image(img_url, caption=f"{row['Year']} {row['Make']} {row['Model']}", use_container_width=True)

            # --- Social Charts ---
            df_social = pd.DataFrame(data["social"])
            df_social["Week"] = ["Week 1","Week 2","Week 3","Week 4"]
            st.markdown("#### 📈 Social Engagement")
            fig_social_line = px.line(df_social, x="Week", y=["Instagram Likes","Facebook Likes","Twitter Retweets"], markers=True, title=f"Social Engagement Demo {i}")
            st.plotly_chart(fig_social_line, use_container_width=True)
            fig_clicks = px.bar(df_social, x="Week", y=["Website Clicks","Leads"], barmode="group", text_auto=True, title=f"Website Clicks & Leads Demo {i}")
            st.plotly_chart(fig_clicks, use_container_width=True)
            last_week = df_social.iloc[-1]
            fig_pie = px.pie(names=["Instagram Likes","Facebook Likes","Twitter Retweets"],
                             values=[last_week["Instagram Likes"], last_week["Facebook Likes"], last_week["Twitter Retweets"]],
                             title=f"Last Week Platform Engagement Demo {i}")
            st.plotly_chart(fig_pie, use_container_width=True)

            # --- Inventory ---
            df_inv = pd.DataFrame(data["inventory"])
            st.markdown("**Inventory Summary**")
            st.table(df_inv)
            st.markdown("**🚘 Inventory Images**")
            inv_cols = st.columns(len(df_inv))
            for idx, row in df_inv.iterrows():
                img_url = get_car_image_url(row["Make"])
                col = inv_cols[idx % len(inv_cols)]
                col.image(img_url, caption=f"{row['Make']} - £{row['Average Price']:,}", use_container_width=True)
            st.info(f"💡 AI Insight: {chart_ai_suggestion(f'Demo Inventory {i}', df_inv.head(3).to_dict(orient='records'))}")

            # --- AI Video Script ---
            st.markdown("### 🎬 AI Video Script Generator")
            sample_listing = df_top.iloc[0]
            demo_script = (
                f"Introducing the {sample_listing['Year']} {sample_listing['Make']} {sample_listing['Model']}!\n"
                "Luxury and performance combined. ✅ High-quality interiors, sleek design, and powerful engine.\n"
                "Perfect for family trips or city driving. 🚗💨\n"
                "Contact us now to book a test drive!"
            )
            st.text_area(f"🎬 Demo Video Script {i}", demo_script, height=150, key=f"demo_script_{i}")
            st.download_button(f"⬇ Download Demo Script {i}", demo_script, file_name=f"{sample_listing['Make']}_{sample_listing['Model']}_demo_script_{i}.txt", key=f"download_demo_script_{i}")

            # --- Competitor Monitoring ---
            st.markdown("### 🏁 Competitor Monitoring (Demo)")
            demo_competitors = pd.DataFrame([
                {"Competitor":"AutoHub","Make":"BMW","Model":"X5","Price":random.randint(47000,50000),"Location":"London"},
                {"Competitor":"CarMax","Make":"Audi","Model":"Q7","Price":random.randint(46000,49000),"Location":"Manchester"},
                {"Competitor":"MotorWorld","Make":"Mercedes","Model":"GLE","Price":random.randint(53000,56000),"Location":"Birmingham"}
            ])
            st.dataframe(demo_competitors)
            st.download_button(f"⬇ Download Competitor Data {i}", demo_competitors.to_csv(index=False), file_name=f"competitor_demo_data_{i}.csv", key=f"download_competitor_{i}")

            # --- Weekly Content Calendar ---
            st.markdown("### 📅 Weekly Content Calendar (Demo)")
            demo_calendar = pd.DataFrame({
                "Day":["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
                "Content":[random.choice(["Listing Highlight","Social Post","Video Script","Tips & Tricks","Wrap Up"]) for _ in range(7)],
                "Platform":[random.choice(["Instagram","Facebook","LinkedIn"]) for _ in range(7)]
            })
            st.dataframe(demo_calendar)
            st.download_button(f"⬇ Download Weekly Content Calendar {i}", demo_calendar.to_csv(index=False), file_name=f"weekly_content_calendar_demo_{i}.csv", key=f"download_calendar_{i}")

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
        email_col = next((c for c in df_inventory.columns if c.lower() == "email"), None)
        if not email_col:
            st.error("⚠️ Inventory sheet missing an 'Email' column.")
            st.stop()

        df_inventory[email_col] = df_inventory[email_col].astype(str).str.lower()
        filtered = df_inventory[df_inventory[email_col] == user_email.lower()]
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
