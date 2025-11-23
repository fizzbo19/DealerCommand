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
# OPENAI API KEY (fixed integration)
# ---------------------------------------------------------
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    st.error("⚠️ Missing OpenAI API key. Set `OPENAI_API_KEY` in environment.")
    st.stop()
client = OpenAI(api_key=api_key)

def openai_generate(prompt, model="gpt-4o-mini", temperature=0.7):
    """Generate text from OpenAI using chat completion API."""
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

# ---------------------------------------------------------
# SIDEBAR: Plans + Trial Overview + Platinum Reports
# ---------------------------------------------------------
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
# Custom Report Builder (Platinum) & Helper Functions
# ----------------
def load_custom_reports(email):
    try:
        resp = requests.get(f"{BACKEND_URL}/custom/reports", params={"email": email})
        return resp.json().get("reports", [])
    except Exception as e:
        st.error(f"⚠️ API error fetching custom reports: {e}")
        return []

def apply_report_filters(df, filters):
    if df is None or df.empty or not filters:
        return df
    out = df.copy()
    for col, cond in filters.items():
        if col not in out.columns:
            continue
        try:
            if isinstance(cond, list):
                out = out[out[col].isin(cond)]
            elif isinstance(cond, dict):
                if "min" in cond:
                    out = out[pd.to_numeric(out[col], errors='coerce') >= cond["min"]]
                if "max" in cond:
                    out = out[pd.to_numeric(out[col], errors='coerce') <= cond["max"]]
            else:
                out = out[out[col] == cond]
        except Exception:
            continue
    return out

def safe_to_numeric(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace('£','', regex=False).str.replace(',','', regex=False), errors='coerce')
    return df

def normalize_colname_map(df):
    cols = list(df.columns)
    m = {str(c).strip().lower(): c for c in cols}
    return m

# ----------------
# Sidebar: Custom Report Builder (Platinum)
# ----------------
with st.sidebar.expander("🧰 Custom Report Builder (Platinum)", expanded=False):
    st.markdown("Create & save custom charts (Platinum only).")

    saved_reports = load_custom_reports(user_email)
    st.markdown(f"Saved reports: **{len(saved_reports)}**")

    sidebar_csv = st.file_uploader("(Optional) Upload CSV here", type=["csv"], key="sidebar_csv")
    sidebar_df = None
    sidebar_columns = []
    if sidebar_csv:
        try:
            sidebar_df = pd.read_csv(sidebar_csv)
            sidebar_df.columns = [str(c).strip() for c in sidebar_df.columns]
            sidebar_columns = list(sidebar_df.columns)
            st.success("CSV loaded for building reports.")
        except Exception as e:
            st.error(f"Failed to load CSV: {e}")

    if not sidebar_columns:
        try:
            inventory_list = api_get_inventory(user_email)
            if inventory_list:
                sidebar_df = pd.DataFrame(inventory_list)
                sidebar_columns = list(sidebar_df.columns)
        except Exception:
            sidebar_columns = []

    st.markdown("### Build new custom report")
    st.markdown("Select columns from the left (Available). Add them to X / Y using the controls.")

    col1, col2 = st.columns([1,1])
    with col1:
        st.markdown("**Available columns**")
        available_cols = st.multiselect("Pick columns", options=sidebar_columns, default=sidebar_columns[:6] if sidebar_columns else [])
    with col2:
        st.markdown("**Axis & Options**")
        x_axis_select = st.selectbox("X axis", options=[""] + available_cols, index=1 if available_cols else 0)
        y_axis_select = st.multiselect("Y axis", options=available_cols, default=[c for c in available_cols if c.lower() in ["price","mileage","revenue","impressions"]][:2])
        chart_type = st.selectbox("Chart Type", ["Line","Bar","Area","Scatter","Table"])
        save_report_name = st.text_input("Report name", value=f"report-{uuid.uuid4().hex[:6]}")

    filters_input = st.text_area("Filters JSON", value='')

    if st.button("Preview this report (local preview)"):
        if sidebar_df is None:
            inventory_list = api_get_inventory(user_email)
            sidebar_df = pd.DataFrame(inventory_list) if inventory_list else None

        if sidebar_df is None or sidebar_df.empty:
            st.warning("No data available to preview.")
        else:
            df_preview = sidebar_df.copy()
            df_preview.columns = [str(c).strip() for c in df_preview.columns]
            try:
                parsed_filters = json.loads(filters_input) if filters_input.strip() else {}
            except Exception as e:
                st.error(f"Invalid filters JSON: {e}")
                parsed_filters = {}
            df_preview = apply_report_filters(df_preview, parsed_filters)
            x_axis = x_axis_select if x_axis_select in df_preview.columns else (df_preview.columns[0] if len(df_preview.columns)>0 else None)
            y_cols = [y for y in y_axis_select if y in df_preview.columns]
            if not y_cols:
                numeric_cols = df_preview.select_dtypes(include=["number"]).columns.tolist()
                y_cols = numeric_cols[:2] if numeric_cols else df_preview.columns[:1].tolist()
            df_preview = safe_to_numeric(df_preview, y_cols)
            try:
                if chart_type == "Table":
                    st.table(df_preview[[x_axis]+y_cols].head(50))
                elif chart_type == "Line":
                    fig = px.line(df_preview, x=x_axis, y=y_cols, markers=True)
                    st.plotly_chart(fig, use_container_width=True)
                elif chart_type == "Bar":
                    fig = px.bar(df_preview, x=x_axis, y=y_cols)
                    st.plotly_chart(fig, use_container_width=True)
                elif chart_type == "Scatter":
                    fig = px.scatter(df_preview, x=x_axis, y=y_cols[0] if y_cols else None)
                    st.plotly_chart(fig, use_container_width=True)
                elif chart_type == "Area":
                    fig = px.area(df_preview, x=x_axis, y=y_cols)
                    st.plotly_chart(fig, use_container_width=True)
                st.success("Preview generated.")
            except Exception as e:
                st.error(f"Failed to render preview: {e}")

    if st.button("💾 Save Custom Report (Platinum)"):
        if current_plan != "platinum":
            st.warning("Upgrade to Platinum to save custom reports.")
        else:
            try:
                filters = json.loads(filters_input) if filters_input.strip() else {}
            except Exception as e:
                st.error(f"Invalid JSON for filters: {e}")
                filters = {}
            config = {
                "chart_type": chart_type,
                "x_axis": x_axis_select or (available_cols[0] if available_cols else ""),
                "y_axis": y_axis_select,
                "filters": filters,
                "name": save_report_name
            }
            ok, msg = api_save_custom_report(user_email, config)
            if ok:
                st.success("✅ Report saved.")
            else:
                st.error(f"⚠️ {msg}")

# ----------------
# MAIN TABS
# ----------------
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
Features: {features}.
Notes: {notes}.
"""
                listing_text = openai_generate(prompt)
                st.markdown("#### Generated Listing")
                st.markdown(listing_text)
                inventory_item = {
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
                    "Generated_Listing": listing_text,
                    "Created": datetime.utcnow().isoformat()
                }
                api_save_inventory(user_email, inventory_item)
                api_increment_platinum_usage(user_email)
                st.success("✅ Listing saved to inventory!")

# ----------------
# ANALYTICS DASHBOARD
# ----------------
with main_tabs[1]:
    st.markdown("### 📊 Analytics Dashboard")
    try:
        inventory_list = api_get_inventory(user_email)
        if inventory_list:
            df = pd.DataFrame(inventory_list)
            analytics_dashboard(df)
        else:
            st.info("No inventory yet. Generate listings to see analytics.")
    except Exception as e:
        st.error(f"Failed to load analytics: {e}")

# ----------------
# INVENTORY VIEW
# ----------------
with main_tabs[2]:
    st.markdown("### 📦 Inventory")
    inventory_list = api_get_inventory(user_email)
    if inventory_list:
        df_inventory = pd.DataFrame(inventory_list)
        st.dataframe(df_inventory)
    else:
        st.info("No inventory yet. Generate listings to populate inventory.")


