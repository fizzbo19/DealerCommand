# frontend/app.py
import sys
import os

# ---------------------------------------------------------
# PATH SETUP
# ---------------------------------------------------------
# Add the repo root to sys.path so 'backend' can be imported
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# ---------------------------------------------------------
# STANDARD LIBRARIES
# ---------------------------------------------------------
import io
import json
import random
import zipfile
import uuid
from datetime import datetime, timedelta

# ---------------------------------------------------------
# THIRD-PARTY LIBRARIES
# ---------------------------------------------------------
import streamlit as st
import pandas as pd
import plotly.express as px
from openai import OpenAI

# ---------------------------------------------------------
# LOCAL IMPORTS (backend helpers)
# ---------------------------------------------------------
from backend.trial_manager import (
    get_dealership_status,
    check_listing_limit,
    increment_usage,
    can_user_login
)
from backend.sheet_utils import (
    append_to_google_sheet,
    get_sheet_data,
    get_inventory_for_user
)
from backend.plan_utils import has_feature
from backend.stripe_utils import create_checkout_session, api_get_inventory
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
# Analytics helper functions for Streamlit (paste above MAIN TABS)
# ----------------

def _safe_parse_datetime(col):
    """Safely parse a timestamp-like column to datetime (in-place)"""
    try:
        return pd.to_datetime(col, errors="coerce")
    except Exception:
        return col

def plotly_chart_for_streamlit(chart_type, df, x=None, y=None, title=None, color=None, size=None, hover_data=None):
    """
    Unified helper for rendering Plotly charts in Streamlit.
    - chart_type: 'line','bar','scatter','hist','pie','area','table'
    - df: pandas DataFrame
    - x,y: column names
    - color: color column
    - size: size column for scatter
    - hover_data: list of columns to show in hover
    """
    try:
        if chart_type == "line":
            fig = px.line(df, x=x, y=y, color=color, markers=True, title=title)
        elif chart_type == "bar":
            fig = px.bar(df, x=x, y=y, color=color, title=title)
        elif chart_type == "scatter":
            fig = px.scatter(df, x=x, y=y, color=color, size=size, hover_data=hover_data, title=title)
        elif chart_type == "hist":
            fig = px.histogram(df, x=x, nbins=30, title=title)
        elif chart_type == "pie":
            fig = px.pie(df, names=x, values=y, title=title)
        elif chart_type == "area":
            fig = px.area(df, x=x, y=y, title=title)
        elif chart_type == "table":
            # small table representation
            fig = None
            st.table(df.head(100))
            return
        else:
            st.write("Unsupported chart type.")
            return

        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Failed to render chart: {e}")

def weekly_monthly_report_dfs(email, inventory_df=None):
    """
    Returns two DataFrames:
      - weekly_counts: listings per week (week starting date, count)
      - monthly_counts: listings per month (YYYY-MM, count)
    Uses Inventory -> Timestamp column if available.
    """
    try:
        if inventory_df is None:
            inventory_df = get_sheet_data("Inventory") if 'get_sheet_data' in globals() else pd.DataFrame()
        if inventory_df is None or inventory_df.empty:
            return pd.DataFrame(), pd.DataFrame()

        # attempt several timestamp columns
        if "Timestamp" in inventory_df.columns:
            inventory_df["Timestamp_parsed"] = _safe_parse_datetime(inventory_df["Timestamp"])
        elif "Created_At" in inventory_df.columns:
            inventory_df["Timestamp_parsed"] = _safe_parse_datetime(inventory_df["Created_At"])
        else:
            # fallback: try to create a synthetic timestamp if index or Created exists
            inventory_df["Timestamp_parsed"] = pd.to_datetime(inventory_df.get("Timestamp", pd.NaT), errors="coerce")

        df = inventory_df.dropna(subset=["Timestamp_parsed"]).copy()
        if df.empty:
            return pd.DataFrame(), pd.DataFrame()

        df["Week"] = df["Timestamp_parsed"].dt.to_period("W").apply(lambda r: r.start_time.date())
        df["Month"] = df["Timestamp_parsed"].dt.to_period("M").astype(str)

        weekly_counts = df.groupby("Week").size().reset_index(name="Listings")
        monthly_counts = df.groupby("Month").size().reset_index(name="Listings")

        return weekly_counts, monthly_counts
    except Exception as e:
        st.error(f"Failed to build weekly/monthly reports: {e}")
        return pd.DataFrame(), pd.DataFrame()

def safe_get_inventory_for_user(email):
    """Try the preferred inventory helper then fallback to sheet read."""
    try:
        df = get_inventory_for_user(email)
        # if get_inventory_for_user returns DataFrame already - return
        if isinstance(df, pd.DataFrame):
            return df
    except Exception:
        pass
    # fallback
    try:
        df_raw = get_sheet_data("Inventory")
        if df_raw is None or df_raw.empty:
            return pd.DataFrame()
        df_raw.columns = [str(c).strip() for c in df_raw.columns]
        email_col = next((c for c in df_raw.columns if str(c).strip().lower() == "email"), None)
        if email_col:
            return df_raw[df_raw[email_col].astype(str).str.lower() == email.lower()].copy()
        # if no email column, return whole sheet
        return df_raw.copy()
    except Exception:
        return pd.DataFrame()


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
# ANALYTICS DASHBOARD (REPLACEMENT)
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
        try:
            # small wrapper to call your existing analytics helper if available
            prompt_sample = sample_data if isinstance(sample_data, str) else str(sample_data)
            return openai_generate(f"You are an automotive analyst. Provide one concise insight about {chart_name} given sample: {prompt_sample}")
        except Exception:
            return ""

    # Load source data (either uploaded CSV or inventory for user)
    if dealer_csv is not None:
        try:
            dealer_df = pd.read_csv(dealer_csv)
            st.success("✅ Dealer inventory CSV loaded. Generating custom dashboard...")
        except Exception as e:
            st.error(f"Failed to read uploaded CSV: {e}")
            dealer_df = pd.DataFrame()
    else:
        # Use inventory from sheets/backend
        dealer_df = safe_get_inventory_for_user(user_email)

    # Normalize columns early
    if dealer_df is None:
        dealer_df = pd.DataFrame()
    if not dealer_df.empty:
        dealer_df.columns = [str(c).strip() for c in dealer_df.columns]

    # Show KPIs
    if not dealer_df.empty:
        st.markdown("#### Dealer Inventory Summary")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Cars", len(dealer_df))
        try:
            price_col = next((c for c in dealer_df.columns if str(c).strip().lower() == "price"), None)
            if price_col:
                price_nums = pd.to_numeric(dealer_df[price_col].astype(str).str.replace('£','', regex=False).str.replace(',','', regex=False), errors='coerce')
                avg_price = int(price_nums.mean()) if not price_nums.dropna().empty else 0
            else:
                avg_price = 0
        except Exception:
            avg_price = 0
        col2.metric("Average Price", f"£{avg_price:,}" if avg_price else "£0")
        try:
            mileage_col = next((c for c in dealer_df.columns if str(c).strip().lower() == "mileage"), None)
            if mileage_col:
                mileage_nums = pd.to_numeric(dealer_df[mileage_col].astype(str).str.replace(" miles","", regex=False).str.replace(',','', regex=False), errors='coerce')
                avg_mileage = int(mileage_nums.mean()) if not mileage_nums.dropna().empty else 0
            else:
                avg_mileage = 0
        except Exception:
            avg_mileage = 0
        col3.metric("Average Mileage", f"{avg_mileage:,} miles" if avg_mileage else "-")
        try:
            col4.metric("Most Common Make", dealer_df['Make'].mode()[0] if "Make" in dealer_df.columns and len(dealer_df)>0 else "-")
        except Exception:
            col4.metric("Most Common Make", "-")

        st.markdown("---")

        # Price distribution
        if price_col:
            try:
                dealer_df["Price_numeric"] = pd.to_numeric(dealer_df[price_col].astype(str).str.replace('£','', regex=False).str.replace(',','', regex=False), errors='coerce')
                plotly_chart_for_streamlit("hist", dealer_df, x="Price_numeric", title="Price Distribution")
                insight = chart_ai_suggestion("Price Distribution", dealer_df.head(10).to_dict(orient='records'))
                if insight:
                    st.info(f"💡 AI Insight: {insight}")
            except Exception as e:
                st.warning(f"Price distribution error: {e}")

        # Mileage vs Price scatter
        if "Mileage" in dealer_df.columns and "Price_numeric" in dealer_df.columns:
            try:
                dealer_df["Mileage_numeric"] = pd.to_numeric(dealer_df["Mileage"].astype(str).str.replace(" miles","", regex=False).str.replace(',','', regex=False), errors='coerce')
                plotly_chart_for_streamlit("scatter", dealer_df, x="Mileage_numeric", y="Price_numeric", color="Make", hover_data=["Model","Year"], title="Mileage vs Price")
                insight = chart_ai_suggestion("Mileage vs Price", dealer_df.head(10).to_dict(orient='records'))
                if insight:
                    st.info(f"💡 AI Insight: {insight}")
            except Exception as e:
                st.warning(f"Mileage vs price error: {e}")

        # Listings over time (weekly/monthly)
        weekly_df, monthly_df = weekly_monthly_report_dfs(user_email, dealer_df)
        if not weekly_df.empty:
            plotly_chart_for_streamlit("line", weekly_df, x="Week", y="Listings", title="Listings Per Week")
        if not monthly_df.empty:
            plotly_chart_for_streamlit("bar", monthly_df, x="Month", y="Listings", title="Listings Per Month")

        # Top Makes pie
        if "Make" in dealer_df.columns:
            try:
                make_counts = dealer_df['Make'].value_counts().reset_index()
                make_counts.columns = ["Make","Count"]
                plotly_chart_for_streamlit("pie", make_counts, x="Make", y="Count", title="Inventory by Make")
            except Exception as e:
                st.warning(f"Top makes error: {e}")

        # Export cleaned CSV
        try:
            csv_bytes = dealer_df.to_csv(index=False).encode("utf-8")
            st.download_button("⬇ Download cleaned inventory CSV", csv_bytes, file_name="dealer_inventory_cleaned.csv", mime="text/csv")
        except Exception:
            pass

        # Small table preview
        st.markdown("#### Sample Inventory Rows")
        st.dataframe(dealer_df.head(50))

    else:
        st.info("No inventory data available. Upload a CSV or add listings to your inventory.")

    # --------------------------
    # 5 Demo Dashboards (kept at bottom)
    # --------------------------
    if show_demo_charts:
        st.markdown("---")
        st.markdown("### 🎨 Demo Dashboards for Reference (5 examples)")
        try:
            demo_list = generate_demo_data() if callable(generate_demo_data) else []
            # If generate_demo_data returns a dict of demo frames (inventory/social), show simple examples
            if isinstance(demo_list, dict):
                demo_inv = demo_list.get("inventory")
                demo_social = demo_list.get("social")
                if isinstance(demo_inv, pd.DataFrame):
                    plotly_chart_for_streamlit("bar", demo_inv.assign(idx=range(len(demo_inv))), x="idx", y=demo_inv.columns[0] if len(demo_inv.columns)>0 else None, title="Demo Inventory Snapshot")
                if isinstance(demo_social, pd.DataFrame):
                    plotly_chart_for_streamlit("line", demo_social, x="Date", y="Views", title="Demo Social Views")
            else:
                # fallback static demo rendering from earlier code (keeps original UI)
                for i, data in enumerate([demo1, demo2, demo3, demo4, demo5], start=1):
                    st.markdown(f"## Demo Dashboard {i}")
                    df_top = pd.DataFrame(data["top_recs"])
                    fig_top = px.bar(df_top, x="Model", y="Score", color="Make", text="Score", title=f"Top Recommendations Demo {i}")
                    st.plotly_chart(fig_top, use_container_width=True)
                    social = data["social"]
                    if all(isinstance(v, list) for v in social.values()):
                        df_social = pd.DataFrame(social)
                        df_social["Week"] = [f"Week {k+1}" for k in range(len(df_social))]
                        y_cols = [c for c in df_social.columns if c != "Week"]
                        fig_social = px.line(df_social, x="Week", y=y_cols, markers=True, title=f"Social Trends Demo {i}")
                        st.plotly_chart(fig_social, use_container_width=True)
                    else:
                        st.table(pd.DataFrame([social]))
                    st.markdown("**Inventory Summary**")
                    df_inv = pd.DataFrame(data["inventory"])
                    st.table(df_inv)
                    st.markdown("---")
        except Exception:
            # If any error occurs while rendering demo, fall back to old ui
            pass


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


