# frontend/app.py
import sys, os, io, json
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
import plotly.express as px
from openai import OpenAI
import random
import zipfile
import uuid

# ---------------------------------------------------------
# PATH SETUP
# ---------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.extend([BASE_DIR, BACKEND_DIR])

# ---------------------------------------------------------
# LOCAL IMPORTS (backend helpers you already have)
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
from backend.analytics import analytics_dashboard, generate_demo_data
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
            messages=[{"role":"system","content":"You are a top-tier automotive copywriter and analyst."},
                      {"role":"user","content":prompt}],
            temperature=temperature
        )
        if resp and getattr(resp, "choices", None):
            return resp.choices[0].message.content.strip()
        return ""
    except Exception as e:
        # don't crash the UI for AI insight failures
        st.error(f"⚠️ OpenAI API error: {e}")
        return ""

# ---------------------------------------------------------
# DEALERSHIP LOGIN (trial tracking)
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

TRIAL_EXPIRY_DATE = profile.get("Trial_Expiry")  # expected datetime or None
if TRIAL_EXPIRY_DATE:
    time_remaining = TRIAL_EXPIRY_DATE - datetime.utcnow()
    trial_days_left = max(0, time_remaining.days)
    is_trial_active = time_remaining.total_seconds() > 0
else:
    trial_days_left = 30
    is_trial_active = True

# If trial active, show platinum features for 30 days
current_plan = plan if not is_trial_active else 'platinum'

if not can_user_login(user_email, plan):
    st.error(f"🚫 Seat limit reached for {plan.capitalize()} plan. Please contact account admin or upgrade plan.")
    st.stop()

# FIRST TIME dealer info
if status == "new":
    st.info("👋 Welcome! Please provide your dealership info to start your trial.")
    with st.form("dealer_info_form"):
        dealer_name = st.text_input("Dealership Name")
        dealer_phone = st.text_input("Phone Number")
        dealer_location = st.text_input("Location / City")
        submitted = st.form_submit_button("Save Info")
        if submitted:
            from backend.sheet_utils import save_dealership_profile
            save_dealership_profile(user_email, {
                "Name": dealer_name,
                "Phone": dealer_phone,
                "Location": dealer_location,
            })
            st.success("✅ Dealership info saved!")

# SIDEBAR: Plans + Trial Overview + Platinum Custom Report Builder
st.sidebar.markdown("### 💳 Upgrade Plans")
plans = {
    "Premium": ["Social Media Analytics (basic)", "AI Captions (5/day)", "Inventory Upload (20 cars max)"],
    "Pro": ["Everything in Premium", "Full Social Analytics", "Dealer Performance Score", "AI Video Script Generator", "Compare Cars Analytics", "Export to CSV/Sheets"],
    "Platinum": ["Everything in Pro", "Custom Charts & Report Builder", "Market Price Intelligence", "AI Appraisal", "Automated Sales Forecasting"]
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

# ----------------
# Custom Report Builder (Platinum feature) in Sidebar (collapsible)
# ----------------
with st.sidebar.expander("🧰 Custom Report Builder (Platinum)", expanded=False):
    st.markdown("Create & save custom charts (Platinum only).")
    saved_reports = []
    try:
        # optional: load saved reports from sheet (if you want to show)
        reports_df = get_sheet_data("Reports")
        if reports_df is not None and not reports_df.empty:
            # filter by user
            reports_df.columns = [str(c).strip() for c in reports_df.columns]
            if "Email" in reports_df.columns:
                saved_reports = reports_df[reports_df["Email"].str.lower() == user_email.lower()].to_dict(orient="records")
    except Exception:
        saved_reports = []

    st.markdown(f"Saved reports: {len(saved_reports)}")
    chart_type = st.selectbox("Chart Type", ["Line", "Bar", "Area", "Scatter", "Table"])
    x_axis = st.text_input("X axis (column name)", value="Date")
    y_axis = st.text_input("Y axis (comma separated numeric columns)", value="Price")
    report_name = st.text_input("Save Report As (name)", value=f"report-{uuid.uuid4().hex[:6]}")
    if st.button("Save Custom Report (Platinum)"):
        if current_plan != "platinum":
            st.warning("Upgrade to Platinum to save custom reports.")
        else:
            config = {"chart_type": chart_type, "x_axis": x_axis, "y_axis": [c.strip() for c in y_axis.split(",")], "name": report_name, "created_at": datetime.utcnow().isoformat()}
            append_to_google_sheet("Reports", {"Email": user_email, "Name": report_name, "Config": json.dumps(config), "Created_At": config["created_at"]})
            st.success("✅ Report saved. It will appear in your Reports sheet.")

# ---------------------------------------------------------
# MAIN TABS
# ---------------------------------------------------------
main_tabs = st.tabs(["🧾 Generate Listing", "📊 Analytics Dashboard", "📈 Inventory"])

# ----------------
# GENERATE LISTING
# ----------------
with main_tabs[0]:
    if is_active and (remaining_listings > 0 or current_plan == "platinum"):
        st.markdown("### 🧾 Generate a New Listing")
        with st.form("listing_form"):
            col1, col2 = st.columns(2)
            with col1:
                make = st.text_input("Car Make", "BMW")
                model = st.text_input("Model", "X5 M Sport")
                year = st.text_input("Year", "2021")
                mileage = st.text_input("Mileage", "28,000 miles")
                color = st.text_input("Color", "Black")
                car_image = st.file_uploader("Upload Car Image (optional)", type=["png", "jpg", "jpeg"])
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
Include emojis and SEO-rich phrasing and a short caption for social sharing.
"""
                with st.spinner("🤖 Generating listing..."):
                    listing_text = openai_generate(prompt)
                st.success("✅ Listing generated!")
                st.text_area("Generated Listing", listing_text, height=250)
                st.download_button("⬇ Download Listing", listing_text, file_name=f"{make}_{model}_listing.txt")

                # upload image (best-effort)
                image_link = ""
                if car_image:
                    try:
                        image_link = upload_image_to_drive(car_image, f"{make}_{model}_{datetime.utcnow().isoformat()}.png")
                        if image_link is None:
                            st.warning("⚠️ Image upload unavailable — check Google Drive credentials.")
                    except Exception as e:
                        st.warning(f"⚠️ Image upload failed: {e}")
                        image_link = ""

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
                saved = False
                try:
                    saved = append_to_google_sheet("Inventory", inventory_data)
                except Exception as e:
                    st.error(f"⚠️ Save failed: {e}")
                if saved:
                    st.success("✅ Listing saved!")
                    try:
                        increment_platinum_usage(user_email, 1)
                    except Exception:
                        pass
                else:
                    st.error("⚠️ Failed to save listing. Check backend sheet_utils.")

    else:
        st.warning("⚠️ Trial ended or listing limit reached. Upgrade to continue.")

# ----------------
# ANALYTICS DASHBOARD (Dealer CSV -> Real analytics + 5 demos bottom)
# ----------------
with main_tabs[1]:
    st.markdown("### 📊 Analytics Dashboard")
    show_demo_charts = st.checkbox("🎨 Show Demo Dashboards (Reference)", value=True, key="show_demo_charts")

    # --- Filter Widgets ---
    all_makes = ["All", "BMW", "Audi", "Mercedes", "Tesla", "Jaguar", "Land Rover", "Porsche"]
    all_models = ["All", "X5 M Sport", "Q7", "GLE", "Q8", "X6", "GLC", "GLE Coupe", "X3 M", "Q5", "Model X", "iX", "e-tron", "F-Pace", "Discovery", "X4", "Cayenne", "M3", "RS7", "C63 AMG", "S-Class", "7 Series", "A8"]
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        selected_make = st.selectbox("Filter by Make", all_makes)
    with filter_col2:
        selected_model = st.selectbox("Filter by Model", all_models)

    # Dealer CSV upload
    st.markdown("### 🔁 Upload your dealer inventory CSV (optional)")
    dealer_csv = st.file_uploader("Upload CSV — generates a custom dashboard", type=["csv"], key="dealer_inventory_upload")

    def chart_ai_suggestion(chart_name, sample_data):
        prompt = f"""
You are an automotive sales analyst. Here is sample inventory data:
{sample_data}
Provide one concise insight about {chart_name} and one actionable suggestion to improve performance.
"""
        return openai_generate(prompt)

    # If dealer CSV uploaded -> show real analytics
    if dealer_csv is not None:
        try:
            dealer_df = pd.read_csv(dealer_csv)
            st.success("✅ Dealer inventory loaded. Generating custom dashboard...")

            # Clean numeric columns (defensive)
            if "Price" in dealer_df.columns:
                dealer_df["Price_numeric"] = pd.to_numeric(dealer_df["Price"].astype(str).str.replace('£','', regex=False).str.replace(',','', regex=False), errors='coerce')
            else:
                dealer_df["Price_numeric"] = pd.Series([0]*len(dealer_df))

            if "Mileage" in dealer_df.columns:
                dealer_df["Mileage_numeric"] = pd.to_numeric(dealer_df["Mileage"].astype(str).str.replace(" miles","", regex=False).str.replace(",","", regex=False), errors='coerce')
            else:
                dealer_df["Mileage_numeric"] = pd.Series([0]*len(dealer_df))

            if "Timestamp" in dealer_df.columns:
                dealer_df["Timestamp"] = pd.to_datetime(dealer_df["Timestamp"], errors='coerce')
                dealer_df["Date"] = dealer_df["Timestamp"].dt.date
            else:
                dealer_df["Date"] = pd.date_range(end=datetime.today(), periods=len(dealer_df)).date

            # --- Summary KPIs
            st.markdown("#### Dealer Inventory Summary")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Cars", len(dealer_df))
            col2.metric("Average Price", f"£{int(dealer_df['Price_numeric'].mean()):,}" if len(dealer_df)>0 else "£0")
            col3.metric("Average Mileage", f"{int(dealer_df['Mileage_numeric'].mean()):,} miles" if len(dealer_df)>0 else "-")
            col4.metric("Most Common Make", dealer_df['Make'].mode()[0] if "Make" in dealer_df.columns and len(dealer_df)>0 else "-")

            # --- Price Distribution
            if "Price_numeric" in dealer_df.columns:
                st.markdown("#### 🏷 Price Distribution")
                fig_price = px.histogram(dealer_df, x="Price_numeric", nbins=20, title="Price Distribution")
                st.plotly_chart(fig_price, use_container_width=True)
                try:
                    insight = chart_ai_suggestion("Price Distribution", dealer_df.head(10).to_dict(orient='records'))
                    st.info(f"💡 AI Insight: {insight}")
                except Exception:
                    pass

            # --- Mileage vs Price scatter
            if "Mileage_numeric" in dealer_df.columns and "Price_numeric" in dealer_df.columns:
                st.markdown("#### 🚗 Mileage vs Price")
                fig_mileage = px.scatter(
                    dealer_df,
                    x="Mileage_numeric",
                    y="Price_numeric",
                    color="Make" if "Make" in dealer_df.columns else None,
                    hover_data=["Model","Year"] if "Model" in dealer_df.columns and "Year" in dealer_df.columns else None,
                    title="Mileage vs Price"
                )
                st.plotly_chart(fig_mileage, use_container_width=True)
                try:
                    insight = chart_ai_suggestion("Mileage vs Price", dealer_df.head(10).to_dict(orient='records'))
                    st.info(f"💡 AI Insight: {insight}")
                except Exception:
                    pass

            # --- Listings Over Time
            if "Date" in dealer_df.columns:
                st.markdown("#### ⏱ Listings Over Time")
                trends = dealer_df.groupby("Date").size().reset_index(name="Listings")
                # convert potential Periods to string to avoid serialization issues
                trends["Date"] = trends["Date"].astype(str)
                fig_trends = px.line(trends, x="Date", y="Listings", title="Listings Added Over Time", markers=True)
                st.plotly_chart(fig_trends, use_container_width=True)
                try:
                    insight = chart_ai_suggestion("Listings Over Time", dealer_df.head(10).to_dict(orient='records'))
                    st.info(f"💡 AI Insight: {insight}")
                except Exception:
                    pass

            # --- Top Makes pie
            if "Make" in dealer_df.columns:
                st.markdown("#### 🏆 Top Makes")
                make_counts = dealer_df['Make'].value_counts().reset_index()
                make_counts.columns = ["Make","Count"]
                fig_make = px.pie(make_counts, names="Make", values="Count", title="Inventory by Make")
                st.plotly_chart(fig_make, use_container_width=True)
                try:
                    insight = chart_ai_suggestion("Top Makes", dealer_df.head(10).to_dict(orient='records'))
                    st.info(f"💡 AI Insight: {insight}")
                except Exception:
                    pass

            # Allow export of cleaned dataframe
            csv_bytes = dealer_df.to_csv(index=False).encode("utf-8")
            st.download_button("⬇ Download cleaned inventory CSV", csv_bytes, file_name="dealer_inventory_cleaned.csv", mime="text/csv")

        except Exception as e:
            st.error(f"⚠️ Error generating analytics: {e}")

    else:
        st.info("Upload a CSV to generate personalised analytics. You can still view demo dashboards below for reference.")

    # --------------------------
    # 5 Distinct Demo Dashboards (kept at bottom)
    # --------------------------
    if show_demo_charts:
        st.markdown("---")
        st.markdown("### 🎨 Demo Dashboards for Reference (5 examples)")

        # Demo 1: Lead Generation Performance
        demo1 = {
            "top_recs": [{"Make":"BMW","Model":"X5","Year":2021,"Score":92}, {"Make":"Audi","Model":"Q7","Year":2022,"Score":88}, {"Make":"Mercedes","Model":"GLE","Year":2020,"Score":85}],
            "social": {"Leads":[50,60,55,70],"Clicks":[400,450,480,520],"Impressions":[5000,5200,5400,6000]},
            "inventory": [{"Make":"BMW","Count":6,"Average Price":52000},{"Make":"Audi","Count":4,"Average Price":49000}]
        }

        # Demo 2: Social Media Growth
        demo2 = {
            "top_recs": [{"Make":"Tesla","Model":"Model X","Year":2021,"Score":90},{"Make":"BMW","Model":"iX","Year":2022,"Score":85}],
            "social": {"Instagram":[1200,1400,1700,2100],"TikTok":[800,900,1200,1800],"Facebook":[700,760,800,820]},
            "inventory": [{"Make":"Tesla","Count":5,"Average Price":70000},{"Make":"BMW","Count":3,"Average Price":65000}]
        }

        # Demo 3: Inventory Health
        demo3 = {
            "top_recs": [{"Make":"Toyota","Model":"Corolla","Year":2019,"Score":78},{"Make":"Ford","Model":"Focus","Year":2018,"Score":72}],
            "social": {"Days_in_Stock":[10,45,32,60],"Price_Reductions":[1,3,2,4]},
            "inventory": [{"Make":"Toyota","Count":8,"Average Price":15000},{"Make":"Ford","Count":5,"Average Price":12000}]
        }

        # Demo 4: Sales Team Performance
        demo4 = {
            "top_recs": [{"Make":"Mercedes","Model":"C-Class","Year":2022,"Score":88},{"Make":"Audi","Model":"A3","Year":2021,"Score":82}],
            "social": {"Rep1_Leads":[10,12,15,20],"Rep2_Leads":[8,9,10,12],"Conversions":[2,3,4,5]},
            "inventory": [{"Make":"Mercedes","Count":4,"Average Price":42000},{"Make":"Audi","Count":6,"Average Price":37000}]
        }

        # Demo 5: Market Competitor Insights
        demo5 = {
            "top_recs": [{"Make":"Porsche","Model":"Cayenne","Year":2022,"Score":95},{"Make":"BMW","Model":"X6","Year":2021,"Score":88}],
            "social": {"Market_Price":[72000,71000,70500,70000],"Availability":[20,18,15,12]},
            "inventory": [{"Make":"Porsche","Count":3,"Average Price":75000},{"Make":"BMW","Count":2,"Average Price":68000}]
        }

        demo_list = [demo1, demo2, demo3, demo4, demo5]

        for i, data in enumerate(demo_list, start=1):
            st.markdown(f"## Demo Dashboard {i}")
            df_top = pd.DataFrame(data["top_recs"])
            # filters
            if selected_make != "All" and selected_make not in df_top["Make"].values:
                continue
            if selected_model != "All" and selected_model not in df_top["Model"].values:
                continue

            # Top recs bar
            fig_top = px.bar(df_top, x="Model", y="Score", color="Make", text="Score", title=f"Top Recommendations Demo {i}")
            st.plotly_chart(fig_top, use_container_width=True)

            # Social visuals vary by demo
            social = data["social"]
            df_social = pd.DataFrame(social)
            # if it's a dict with lists -> turn into table with Week
            if all(isinstance(v, list) for v in social.values()):
                df_social = pd.DataFrame(social)
                df_social["Week"] = [f"Week {k+1}" for k in range(len(df_social))]
                y_cols = [c for c in df_social.columns if c != "Week"]
                fig_social = px.line(df_social, x="Week", y=y_cols, title=f"Social Trends Demo {i}", markers=True)
                st.plotly_chart(fig_social, use_container_width=True)
            else:
                # single-value lists or numeric -> show table
                st.table(pd.DataFrame([social]))

            # Inventory table
            st.markdown("**Inventory Summary**")
            df_inv = pd.DataFrame(data["inventory"])
            st.table(df_inv)

            # Small AI suggestion (best-effort)
            try:
                sample = df_top.head(3).to_dict(orient="records")
                insight = chart_ai_suggestion(f"Demo {i} Top Recommendations", sample)
                st.info(f"💡 AI Insight (demo): {insight}")
            except Exception:
                pass

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
            details = {k: row.get(k, "-") for k in ["Mileage", "Color", "Fuel", "Transmission", "Price", "Features", "Notes"]}
            st.table(pd.DataFrame(details.items(), columns=["Attribute", "Value"]))
            st.markdown("#### Listing Description")
            st.write(row.get("Listing", "No description found."))
            st.markdown("---")
    except Exception as e:
        st.error(f"⚠️ Error loading inventory: {e}")

