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
# LOCAL IMPORTS (backend helpers)
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
    generate_weekly_content_calendar,
    save_custom_report, 
    load_custom_reports, 
    apply_report_filters

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
# Custom Report Builder (Platinum feature) in Sidebar
# ----------------
with st.sidebar.expander("🧰 Custom Report Builder (Platinum)", expanded=False):
    st.markdown("Create & save custom charts (Platinum only).")

    # Load saved reports for this user
    saved_reports = load_custom_reports(user_email)
    st.markdown(f"Saved reports: {len(saved_reports)}")
    
    # Select a saved report to preview
    report_names = [r["name"] for r in saved_reports]
    selected_saved_report = st.selectbox("Select a saved report to preview", ["-- None --"] + report_names)
    # Preview selected saved report
if selected_saved_report != "-- None --":
    report_to_preview = next((r for r in saved_reports if r["name"] == selected_saved_report), None)
    if report_to_preview:
        config = report_to_preview.get("config", {})
        df_inventory = get_sheet_data("Inventory")
        if df_inventory is not None and not df_inventory.empty:
            df_inventory.columns = [str(c).strip() for c in df_inventory.columns]
            df_inventory = df_inventory[df_inventory.columns].copy()
            
            # Filter inventory by user
            email_col = next((c for c in df_inventory.columns if c.lower() == "email"), None)
            if email_col:
                df_inventory = df_inventory[df_inventory[email_col].str.lower() == user_email.lower()]
            
            # Apply filters
            df_filtered = apply_report_filters(df_inventory, config.get("filters", {}))
            
            if df_filtered.empty:
                st.info("No inventory matches the selected report filters.")
            else:
                st.markdown(f"### Preview: {selected_saved_report}")
                chart_type = config.get("chart_type", "Bar")
                x_col = config.get("x_axis", "Date")
                y_cols = config.get("y_axis", ["Price"])
                
                import plotly.express as px
                try:
                    if chart_type.lower() == "table":
                        st.table(df_filtered[[x_col] + y_cols] if x_col in df_filtered.columns else df_filtered[y_cols])
                    else:
                        fig = px.line(df_filtered, x=x_col, y=y_cols, title=f"{selected_saved_report} ({chart_type})", markers=True) if chart_type.lower()=="line" else \
                              px.bar(df_filtered, x=x_col, y=y_cols, title=f"{selected_saved_report} ({chart_type})")
                        st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.error(f"⚠️ Error rendering chart: {e}")

    # Create / Save a new report
    st.markdown("### Create a New Custom Report")
    chart_type = st.selectbox("Chart Type", ["Line", "Bar", "Area", "Scatter", "Table"])
    x_axis = st.text_input("X axis (column name)", value="Date")
    y_axis = st.text_input("Y axis (comma separated numeric columns)", value="Price")
    
    # Optional filters JSON
    filters_input = st.text_area("Filters (JSON format)", value='{"Make":["BMW","Audi"],"Year":{"min":2018,"max":2023}}')
    
    report_name = st.text_input("Save Report As (name)", value=f"report-{uuid.uuid4().hex[:6]}")
    
    if st.button("Save Custom Report (Platinum)"):
        if current_plan != "platinum":
            st.warning("Upgrade to Platinum to save custom reports.")
        else:
            try:
                filters = json.loads(filters_input) if filters_input.strip() else {}
            except Exception as e:
                st.error(f"Invalid JSON for filters: {e}")
                filters = {}
            report_config = {
                "chart_type": chart_type,
                "x_axis": x_axis,
                "y_axis": [c.strip() for c in y_axis.split(",")],
                "filters": filters,
                "name": report_name
            }
            success, msg = save_custom_report(user_email, report_config)
            if success:
                st.success("✅ Report saved successfully.")
            else:
                st.error(f"⚠️ {msg}")


# ----------------
# MAIN TABS
# ----------------
main_tabs = st.tabs(["🧾 Generate Listing", "📊 Analytics Dashboard", "📈 Inventory"])

# ----------------
# GENERATE LISTING (unchanged)
# ----------------
# ... keep your existing listing generation code as-is ...

# ----------------
# ANALYTICS DASHBOARD
# ----------------
with main_tabs[1]:
    st.markdown("### 📊 Analytics Dashboard")
    show_demo_charts = st.checkbox("🎨 Show Demo Dashboards (Reference)", value=True, key="show_demo_charts")

    # Filter widgets
    all_makes = ["All", "BMW", "Audi", "Mercedes", "Tesla", "Jaguar", "Land Rover", "Porsche"]
    all_models = ["All", "X5 M Sport", "Q7", "GLE", "Q8", "X6", "GLC", "GLE Coupe", "X3 M", "Q5", "Model X", "iX", "e-tron", "F-Pace", "Discovery", "X4", "Cayenne", "M3", "RS7", "C63 AMG", "S-Class", "7 Series", "A8"]
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        selected_make = st.selectbox("Filter by Make", all_makes)
    with filter_col2:
        selected_model = st.selectbox("Filter by Model", all_models)

    dealer_csv = st.file_uploader("Upload CSV — generates a custom dashboard", type=["csv"], key="dealer_inventory_upload")

    def chart_ai_suggestion(chart_name, sample_data):
        prompt = f"""
You are an automotive sales analyst. Here is sample inventory data:
{sample_data}
Provide one concise insight about {chart_name} and one actionable suggestion to improve performance.
"""
        return openai_generate(prompt)

    if dealer_csv is not None:
        try:
            dealer_df = pd.read_csv(dealer_csv)
            st.success("✅ Dealer inventory loaded. Generating custom dashboard...")

            # Clean numeric columns
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

            # Summary KPIs
            st.markdown("#### Dealer Inventory Summary")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Cars", len(dealer_df))
            col2.metric("Average Price", f"£{int(dealer_df['Price_numeric'].mean()):,}" if len(dealer_df)>0 else "£0")
            col3.metric("Average Mileage", f"{int(dealer_df['Mileage_numeric'].mean()):,} miles" if len(dealer_df)>0 else "-")
            col4.metric("Most Common Make", dealer_df['Make'].mode()[0] if "Make" in dealer_df.columns and len(dealer_df)>0 else "-")

            # Price Distribution
            if "Price_numeric" in dealer_df.columns:
                st.markdown("#### 🏷 Price Distribution")
                fig_price = px.histogram(dealer_df, x="Price_numeric", nbins=20, title="Price Distribution")
                st.plotly_chart(fig_price, use_container_width=True)
                try:
                    insight = chart_ai_suggestion("Price Distribution", dealer_df.head(10).to_dict(orient='records'))
                    st.info(f"💡 AI Insight: {insight}")
                except Exception:
                    pass

            # Mileage vs Price scatter
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

            # Listings Over Time
            if "Date" in dealer_df.columns:
                st.markdown("#### ⏱ Listings Over Time")
                trends = dealer_df.groupby("Date").size().reset_index(name="Listings")
                trends["Date"] = trends["Date"].astype(str)
                fig_trends = px.line(trends, x="Date", y="Listings", title="Listings Added Over Time", markers=True)
                st.plotly_chart(fig_trends, use_container_width=True)
                try:
                    insight = chart_ai_suggestion("Listings Over Time", dealer_df.head(10).to_dict(orient='records'))
                    st.info(f"💡 AI Insight: {insight}")
                except Exception:
                    pass

            # Top Makes
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

            # Export cleaned CSV
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

        # Demo 1-5 data (distinct)
        # ... keep your existing demo1/demo2/demo3/demo4/demo5 dicts as-is ...
        demo_list = [demo1, demo2, demo3, demo4, demo5]

        for i, data in enumerate(demo_list, start=1):
            st.markdown(f"## Demo Dashboard {i}")
            df_top = pd.DataFrame(data["top_recs"])
            if selected_make != "All" and selected_make not in df_top["Make"].values:
                continue
            if selected_model != "All" and selected_model not in df_top["Model"].values:
                continue

            fig_top = px.bar(df_top, x="Model", y="Score", color="Make", text="Score", title=f"Top Recommendations Demo {i}")
            st.plotly_chart(fig_top, use_container_width=True)

            social = data["social"]
            if all(isinstance(v, list) for v in social.values()):
                df_social = pd.DataFrame(social)
                df_social["Week"] = [f"Week {k+1}" for k in range(len(df_social))]
                y_cols = [c for c in df_social.columns if c != "Week"]
                fig_social = px.line(df_social, x="Week", y=y_cols, markers=True, title="Social Media Engagement")
                st.plotly_chart(fig_social, use_container_width=True)

# ----------------
# INVENTORY TAB
# ----------------
with main_tabs[2]:
    st.markdown("### 📦 Dealer Inventory")
    if dealer_csv:
        st.dataframe(dealer_df)
    else:
        st.info("Upload a CSV in the Analytics tab to view inventory here.")

# ----------------
# END OF APP
# ----------------
st.markdown("<br><br><br>", unsafe_allow_html=True)

