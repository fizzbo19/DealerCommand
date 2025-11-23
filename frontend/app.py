import sys, os, io, json
import uuid
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
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
    can_user_login
)
from backend.sheet_utils import append_to_google_sheet, get_sheet_data, get_inventory_for_user
from backend.platinum_manager import (
    can_add_listing,
    increment_platinum_usage,
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
    if isinstance(TRIAL_EXPIRY_DATE, str):
        try:
            TRIAL_EXPIRY_DATE = datetime.fromisoformat(TRIAL_EXPIRY_DATE)
        except Exception:
            TRIAL_EXPIRY_DATE = None

if TRIAL_EXPIRY_DATE:
    time_remaining = TRIAL_EXPIRY_DATE - datetime.utcnow()
    trial_days_left = max(0, time_remaining.days)
    is_trial_active = time_remaining.total_seconds() > 0
else:
    # Fallback if Trial_Expiry is somehow missing or could not be parsed
    trial_days_left = 30
    is_trial_active = True

# current_plan logic simplified to rely on profile status
# If trial is active, grant platinum access regardless of stored plan
current_plan = 'platinum' if is_trial_active else plan

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
    # This should trigger an update via backend logic, simplified here for demo
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


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------

def get_car_image_url(make):
    """
    Returns a simple, labeled image placeholder (600x400) showing the car make 
    for clear context in the demo dashboard.
    """
    text = str(make).split()[0].upper() + "%20CAR"
    # Format: https://placehold.co/{width}x{height}/{background color}/{text color}?text={text}
    return f"https://placehold.co/600x400/31363F/F0F7FF?text={text}"


def get_user_inventory(email):
    """
    Fetches user inventory from the sheet, cleans columns, and parses numeric/date types 
    for dashboard readiness.
    """
    try:
        df = pd.DataFrame(get_inventory_for_user(email))
        
        if df.empty:
            return pd.DataFrame(columns=["Make", "Model", "Year", "Price", "Mileage", "Timestamp"])
        
        df.columns = [str(c).strip() for c in df.columns]

        # Standardize timestamp parsing
        timestamp_col = next((c for c in df.columns if c.lower() in ["timestamp", "created", "created_at"]), None)
        if timestamp_col:
            df["Timestamp_parsed"] = pd.to_datetime(df[timestamp_col], errors="coerce", utc=True)
            df.dropna(subset=["Timestamp_parsed"], inplace=True)
        else:
            df["Timestamp_parsed"] = pd.Timestamp.utcnow() # Fallback

        # Standardize numeric parsing
        for num_col, chars in [("Price", ["£", ","]), ("Mileage", [" miles", ","])]:
            if num_col in df.columns:
                s = df[num_col].astype(str).str.strip()
                for ch in chars:
                    s = s.str.replace(ch, "", regex=False)
                df[f"{num_col}_num"] = pd.to_numeric(s, errors='coerce')
        return df
    except Exception as e:
        print(f"Error in get_user_inventory: {e}")
        return pd.DataFrame()


def weekly_monthly_reports(df):
    """Return weekly and monthly listing counts."""
    if df.empty or "Timestamp_parsed" not in df.columns: 
        return pd.DataFrame(columns=['Week', 'Listings']), pd.DataFrame(columns=['Month', 'Listings'])
    
    df["Week"] = df["Timestamp_parsed"].dt.to_period("W").apply(lambda r: r.start_time.date())
    df["Month"] = df["Timestamp_parsed"].dt.to_period("M").astype(str)
    
    weekly_counts = df.groupby("Week").size().reset_index(name="Listings")
    monthly_counts = df.groupby("Month").size().reset_index(name="Listings")
    return weekly_counts, monthly_counts

def plotly_chart(df, chart_type, x=None, y=None, title=None, color=None, size=None, hover=None):
    """Generates and displays a Plotly chart."""
    if df.empty:
        # Avoid showing st.info here, let the caller decide
        return

    # Check and convert columns to numeric if needed
    for col in [x, y, size]:
        if col and col in df.columns and not pd.api.types.is_numeric_dtype(df[col]):
            df[col] = pd.to_numeric(df[col], errors='coerce')

    try:
        chart_type = chart_type.lower()
        if chart_type == "line":
            fig = px.line(df, x=x, y=y, color=color, markers=True, title=title)
        elif chart_type == "bar" or chart_type == "stacked bar chart":
            fig = px.bar(df, x=x, y=y, color=color, title=title)
        elif chart_type == "scatter" or chart_type == "plot chart":
            fig = px.scatter(df, x=x, y=y, color=color, size=size, hover_data=hover, title=title)
        elif chart_type == "hist":
            fig = px.histogram(df, x=x, nbins=30, title=title)
        elif chart_type == "pie":
            fig = px.pie(df, names=x, values=y, title=title)
        elif chart_type == "area":
            fig = px.area(df, x=x, y=y, title=title)
        else:
            st.warning("Unsupported chart type: " + chart_type)
            return
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Failed to render chart '{title}': {e}")


def render_dashboard(df, title_prefix="Inventory", show_summary=False, filter_make="All", filter_model="All"):
    """Render core analytics charts for real inventory or demo data, including Stale Inventory Analysis."""
    if df.empty:
        st.info(f"No data available for {title_prefix}.")
        return

    # --- Filtering Logic ---
    df_filtered = df.copy()
    if filter_make != "All" and "Make" in df_filtered.columns:
        df_filtered = df_filtered[df_filtered["Make"] == filter_make]
    if filter_model != "All" and "Model" in df_filtered.columns:
        df_filtered = df_filtered[df_filtered["Model"] == filter_model]

    if df_filtered.empty:
        st.info(f"No data matches the selected filters for {title_prefix}.")
        return
    
    # --- Inventory Age Calculation ---
    avg_days = 0
    stale_percent = 0
    stale_action_insight = "Inventory age data is unavailable."
    
    if "Timestamp_parsed" in df_filtered.columns and not df_filtered["Timestamp_parsed"].isnull().all():
        # Ensure comparison is done with timezone-naive datetimes
        df_filtered['Days_On_Lot'] = (datetime.utcnow().replace(tzinfo=None) - df_filtered["Timestamp_parsed"].dt.tz_localize(None)).dt.days
        avg_days = df_filtered['Days_On_Lot'].mean()
        
        # Categorize Inventory Age
        df_filtered['Inventory_Age_Bucket'] = pd.cut(
            df_filtered['Days_On_Lot'],
            bins=[0, 30, 60, 90, df_filtered['Days_On_Lot'].max() + 1],
            labels=['0-30 Days (Fast)', '31-60 Days (Normal)', '61-90 Days (Warning)', '>90 Days (Stale)'],
            right=False
        )
        
        stale_inventory_count = len(df_filtered[df_filtered['Inventory_Age_Bucket'] == '>90 Days (Stale)'])
        total_count = len(df_filtered)
        stale_percent = (stale_inventory_count / total_count) * 100 if total_count > 0 else 0
        
        if stale_percent > 10:
             stale_action_insight = f"Recommend prioritizing markdowns or trade-ins for {stale_inventory_count} units over 90 days old."
        elif stale_percent > 0:
             stale_action_insight = f"Monitor the {stale_inventory_count} units approaching the 90-day threshold."
        else:
             stale_action_insight = "Excellent inventory management with no units exceeding 90 days."


    st.markdown(f"### 📊 {title_prefix} Dashboard")

    # AI Summary for Platinum Users
    if show_summary:
        st.markdown("#### 🤖 AI Analyst Summary")
        if 'Price_num' in df_filtered.columns and not df_filtered['Price_num'].isnull().all():
            avg_price = f"£{int(df_filtered['Price_num'].mean()):,}"
            count = len(df_filtered)
            
            # Updated Prompt with Stale Inventory Data
            summary_prompt = f"""
Analyze the following inventory and market summary and provide a brief (3-4 sentence) summary of key insights and 1 actionable suggestion.
Inventory size: {count}. Average Price: {avg_price}. 
Average Days on Lot: {int(avg_days)} days. Stale Inventory (>90 days): {stale_percent:.1f}%.
Top 3 Makes by Count: {df_filtered['Make'].value_counts().head(3).to_dict() if 'Make' in df_filtered.columns else 'N/A'}.
Actionable Insight: {stale_action_insight}
"""
            with st.spinner("Analyzing data and generating insights..."):
                ai_summary = openai_generate(summary_prompt, model="gpt-4o-mini", temperature=0.6)
            st.info(ai_summary)
        else:
            st.warning("Cannot generate AI summary without valid data.")


    # KPIs - Added Days on Lot and Stale Inventory
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Cars (Filtered)", len(df_filtered))
    col2.metric("Avg Days on Lot", f"{int(avg_days)} days")
    col3.metric("Average Price", f"£{int(df_filtered['Price_num'].mean()):,}" if "Price_num" in df_filtered.columns and not df_filtered['Price_num'].isnull().all() else "-")
    col4.metric("Stale Inventory (>90d)", f"{stale_percent:.1f}%")
    
    # --- New Chart: Inventory Age Bucket ---
    if 'Inventory_Age_Bucket' in df_filtered.columns:
        age_counts = df_filtered['Inventory_Age_Bucket'].value_counts().reset_index()
        age_counts.columns = ['Age_Bucket', 'Count']
        # Order the categories correctly
        age_counts['Age_Bucket'] = pd.Categorical(age_counts['Age_Bucket'], categories=['0-30 Days (Fast)', '31-60 Days (Normal)', '61-90 Days (Warning)', '>90 Days (Stale)'], ordered=True)
        age_counts = age_counts.sort_values('Age_Bucket')
        
        plotly_chart(age_counts, "bar", x="Age_Bucket", y="Count", title=f"{title_prefix}: Inventory Age Distribution", color="Age_Bucket")
        
    # Time-based reports
    weekly_df, monthly_df = weekly_monthly_reports(df_filtered)
    plotly_chart(weekly_df, "line", x="Week", y="Listings", title=f"{title_prefix}: Listings Per Week")
    plotly_chart(monthly_df, "bar", x="Month", y="Listings", title=f"{title_prefix}: Listings Per Month")

    # Price histogram
    if "Price_num" in df_filtered.columns: 
        plotly_chart(df_filtered, "hist", x="Price_num", title=f"{title_prefix}: Price Distribution")
    
    # Mileage vs Price scatter
    if "Mileage_num" in df_filtered.columns and "Price_num" in df_filtered.columns:
        plotly_chart(df_filtered, "scatter", x="Mileage_num", y="Price_num", color="Make", hover=["Model","Year"], title=f"{title_prefix}: Mileage vs Price")
    
    # Make pie chart
    if "Make" in df_filtered.columns:
        make_counts = df_filtered["Make"].value_counts().reset_index()
        make_counts.columns = ["Make","Count"]
        plotly_chart(make_counts, "pie", x="Make", y="Count", title=f"{title_prefix}: Inventory by Make")


def render_custom_report(df, chart_type, x_col, y_col, color_col, size_col, agg_func, title):
    """Dynamically aggregates and renders a custom chart from uploaded data."""
    
    df_report = df.copy()
    
    # Identify numeric and grouping columns
    group_cols = [c for c in [x_col, color_col] if c and c in df_report.columns]
    
    # --- Aggregation Logic (Updated) ---
    if chart_type != 'Table':
        
        y_plot_col = y_col
        
        # 1. Y-Axis Validation and Conversion
        if y_col and y_col not in df_report.columns:
             st.error(f"Y-Axis column '{y_col}' not found in data.")
             return
        if y_col and not pd.api.types.is_numeric_dtype(df_report[y_col]):
            df_report[y_col] = pd.to_numeric(df_report[y_col], errors='coerce') 

        # 2. Determine aggregation method
        agg_map = {
            'SUM': 'sum', 
            'AVERAGE': 'mean', 
            'COUNT': 'count', 
            'MIN': 'min', 
            'MAX': 'max'
        }
        pandas_agg = agg_map.get(agg_func, 'sum') # Default to sum

        if group_cols and y_col and chart_type != 'Pie':
            # Aggregate based on group_cols, using the chosen function on the Y metric
            # Handle the case where COUNT is chosen (the Y value doesn't matter for the count itself)
            if agg_func == 'COUNT':
                 # Use size() for count across groups
                df_agg = df_report.groupby(group_cols, dropna=False).size().reset_index(name='Aggregated_Y')
            else:
                df_agg = df_report.groupby(group_cols, dropna=False)[y_col].agg(pandas_agg).reset_index(name='Aggregated_Y')
            y_plot_col = 'Aggregated_Y'
            
        elif chart_type == 'Pie':
            # Pie charts typically count occurrences of the X-axis category
            df_agg = df_report.groupby(x_col).size().reset_index(name='Count')
            y_plot_col = 'Count'
        else:
            df_agg = df_report
            
    else: # Table type
        df_agg = df_report


    # 2. Render Chart
    if chart_type == 'Table':
        st.subheader(title)
        display_cols = [c for c in [x_col, y_col, color_col, size_col] if c and c in df_report.columns]
        if not display_cols:
             display_cols = df_report.columns.tolist()
        st.dataframe(df_report[display_cols].head(50))
    
    elif chart_type == 'Histogram' and x_col:
        plotly_chart(df_report, "hist", x=x_col, title=title)
    
    elif x_col and y_col:
        chart_map = {
            'Bar Chart': 'bar', 
            'Line Chart': 'line', 
            'Scatter Plot': 'scatter',
            'Area Chart': 'area',
            'Stacked Bar Chart': 'bar', 
            'Plot Chart': 'scatter'
        }
        
        plotly_chart(
            df_agg, 
            chart_map.get(chart_type, 'bar'), 
            x=x_col, 
            y=y_plot_col, 
            color=color_col, 
            size=size_col if chart_type in ['Scatter Plot', 'Plot Chart'] else None, 
            title=title
        )
    else:
        st.error("Please select valid X and Y axes for the selected chart type.")
        return

    # 3. Download Button
    st.download_button(
        f"⬇ Download Custom Report Data ({title})",
        df_report.to_csv(index=False).encode("utf-8"),
        file_name=f"{title.replace(' ', '_')}_report.csv",
        mime="text/csv"
    )


# ----------------
# GENERATE LISTING
# ----------------
with main_tabs[0]:
    if is_active and (remaining_listings > 0 or current_plan=="platinum"):
        st.markdown("### 🧾 Generate a New Listing")
        
        # Form definition 
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
                
                inventory_id = str(uuid.uuid4())
                
                image_link = upload_image_to_drive(car_image, f"{make}_{model}_{datetime.utcnow().isoformat()}.png") if car_image else ""
                
                inventory_data = {
                    "Inventory_ID": inventory_id,
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

    is_platinum_user = (current_plan == 'platinum')

    # Filter widgets (Used for Real Inventory, Custom CSV, and Demo Dashboards)
    all_makes = ["All", "BMW", "Audi", "Mercedes", "Tesla", "Jaguar", "Land Rover", "Porsche"]
    all_models = ["All", "X5 M Sport", "Q7", "GLE", "Q8", "X6", "GLC", "GLE Coupe", "X3 M", "Q5", "Model X", "iX", "e-tron", "F-Pace", "Discovery", "X4", "Cayenne", "M3", "RS7", "C63 AMG", "S-Class", "7 Series", "A8"]
    
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        selected_make = st.selectbox("Filter by Make", all_makes, key="dash_make_filter")
    with filter_col2:
        selected_model = st.selectbox("Filter by Model", all_models, key="dash_model_filter")
        
    dashboard_type = st.selectbox("Select Data Source", ["Real Inventory", "Custom CSV Upload", "Demo Dashboards"])


    if dashboard_type == "Real Inventory":
        df = get_user_inventory(user_email)
        # Pass filters and AI summary flag
        render_dashboard(df, title_prefix="Inventory", show_summary=is_platinum_user, filter_make=selected_make, filter_model=selected_model)
        
    elif dashboard_type == "Custom CSV Upload":
        st.markdown("#### ⬆️ Upload Your Inventory CSV (Custom Report Builder)")
        
        if not is_platinum_user:
            st.warning("🔒 The Custom CSV Upload and Report Builder feature is exclusive to Platinum users (available during your free trial).")
            
        uploaded_file = st.file_uploader("Choose an Inventory CSV file", type=["csv"], key="custom_csv_uploader")
        
        if uploaded_file is not None:
            if 'df_custom_upload_name' not in st.session_state or st.session_state['df_custom_upload_name'] != uploaded_file.name:
                # 1. Load and parse CSV data and store in session state (only if new file)
                try:
                    df_custom = pd.read_csv(uploaded_file)
                    df_custom.columns = [str(c).strip() for c in df_custom.columns]
                    
                    # Apply data cleaning (similar to get_user_inventory)
                    df_custom['Price_num'] = pd.to_numeric(df_custom.get('Price', pd.Series()).astype(str).str.replace('£', '', regex=False).str.replace(',', '', regex=False), errors='coerce')
                    df_custom['Mileage_num'] = pd.to_numeric(df_custom.get('Mileage', pd.Series()).astype(str).str.replace(' miles', '', regex=False).str.replace(',', '', regex=False), errors='coerce')
                    
                    if 'Timestamp' in df_custom.columns:
                        df_custom['Timestamp_parsed'] = pd.to_datetime(df_custom['Timestamp'], errors='coerce', utc=True)
                    else:
                        df_custom['Timestamp_parsed'] = datetime.utcnow()
                    
                    st.session_state['df_custom_upload'] = df_custom
                    st.session_state['df_custom_upload_name'] = uploaded_file.name
                    st.success("✅ CSV loaded. Ready to build custom reports.")
                except Exception as e:
                    st.error(f"⚠️ Error loading or processing CSV file: {e}")
                    st.session_state['df_custom_upload'] = pd.DataFrame()
                    st.session_state['df_custom_upload_name'] = None

            # 2. Custom Report Builder UI (Only render if Platinum)
            if is_platinum_user and 'df_custom_upload' in st.session_state and not st.session_state['df_custom_upload'].empty:
                df_available = st.session_state['df_custom_upload']
                available_cols = df_available.columns.tolist()

                st.markdown("---")
                st.markdown("#### 🛠️ Custom Report Builder")
                
                with st.container(border=True):
                    st.subheader("Chart Parameters (Drag & Drop Metrics)")
                    col_chart, col_x, col_y = st.columns(3)

                    chart_options = ['Table', 'Bar Chart', 'Line Chart', 'Scatter Plot', 'Pie Chart', 'Histogram', 'Area Chart', 'Stacked Bar Chart', 'Plot Chart']
                    
                    chart_type = col_chart.selectbox("Select Chart Type", 
                                                     chart_options, 
                                                     key="report_chart_type")
                    
                    x_axis = col_x.selectbox("X-Axis (Category/Time/Value)", 
                                             [''] + available_cols, 
                                             key="report_x_axis")
                    
                    y_axis_options = [''] + [col for col in available_cols if 'num' in col or df_available[col].dtype in ['int64', 'float64']]
                    if not y_axis_options:
                        y_axis_options = [''] + available_cols # Fallback if no numeric columns detected
                        
                    y_axis = col_y.selectbox("Y-Axis (Value)", 
                                             y_axis_options, 
                                             key="report_y_axis")
                    
                    col_agg, col_color, col_size = st.columns(3)
                    
                    agg_func = col_agg.selectbox("Aggregation Function",
                                                 ['SUM', 'AVERAGE', 'COUNT', 'MIN', 'MAX'],
                                                 key="report_agg_func")
                                                 
                    color_by = col_color.selectbox("Color/Grouping (e.g., Make)", 
                                                    [''] + [col for col in available_cols if df_available[col].nunique() < 50], 
                                                    key="report_color")
                    
                    size_by = col_size.selectbox("Size (Scatter/Plot only)", 
                                                 y_axis_options, 
                                                 key="report_size")
                    
                    report_title = st.text_input("Report Title", f"Custom Analysis of {st.session_state['df_custom_upload_name']}", key="report_title")

                    generate_btn = st.button("Generate Custom Report", key="generate_custom_report_btn")
                
                if generate_btn:
                    # Basic validation for chart types
                    if chart_type in ['Table', 'Histogram']:
                        is_valid = True
                    elif chart_type == 'Pie' and x_axis:
                        is_valid = True
                    elif x_axis and y_axis:
                        is_valid = True
                    else:
                        st.error("Please select a Chart Type, X-Axis, and Y-Axis for plotting.")
                        is_valid = False

                    if is_valid:
                        render_custom_report(df_available, chart_type, x_axis, y_axis, color_by, size_by, agg_func, report_title)
            
        
    elif dashboard_type == "Demo Dashboards":
        if is_platinum_user:
            st.info("Showing Demo Dashboards (Platinum Feature - Includes AI Analysis).")
            show_summary = True
        else:
            st.info("Showing Demo Dashboards. Upgrade to Platinum for AI Summary features.")
            show_summary = False

        # NOTE: Simple demo data generator used here for consistency
        def generate_demo_data(seed=42, n=50):
            random.seed(seed)
            makes = ["BMW", "Audi", "Mercedes", "Tesla", "Porsche", "Jaguar", "Land Rover"]
            models = ["X5", "Q7", "GLE", "Model S", "Cayenne", "F-Pace", "Discovery"]
            data = []
            for _ in range(n):
                make = random.choice(makes)
                data.append({
                    "Make": make, 
                    "Model": random.choice(models), 
                    "Year": random.randint(2018, 2023),
                    "Price_num": random.randint(40000, 90000),
                    "Mileage_num": random.randint(5000, 50000),
                    "Timestamp_parsed": datetime.utcnow() - timedelta(days=random.randint(1, 365))
                })
            df = pd.DataFrame(data)
            df['Price'] = df['Price_num'].apply(lambda x: f"£{x:,}") # Recreate original format for display
            df['Mileage'] = df['Mileage_num'].apply(lambda x: f"{x:,} miles")
            return df
        
        # Define 5 Demo Dashboards with unique themes/seeds
        demo_seeds = {
            "1. Luxury SUV Market": 101,
            "2. EV Segment Performance": 202,
            "3. High-Mileage Price Elasticity": 303,
            "4. Sport/Performance Models": 404,
            "5. Inventory Age & Listing Trend": 505
        }
        
        for name, seed in demo_seeds.items():
            st.markdown(f"## {name}")
            
            # Use the simple generator for consistent data format
            demo_df = generate_demo_data(seed=seed) 
            
            # Apply demo-specific filtering if selected
            render_dashboard(
                df=demo_df, 
                title_prefix=f"Demo: {name}", 
                show_summary=show_summary,
                filter_make=selected_make, 
                filter_model=selected_model
            )
            
            # Example car images for visual interest (Always shows filtered makes if possible)
            unique_makes = demo_df['Make'].unique()
            img_cols = st.columns(min(len(unique_makes), 5))
            st.markdown("**🚗 Sample Car Images**")
            
            display_makes = [m for m in unique_makes if selected_make == 'All' or m == selected_make]
            
            for idx, make in enumerate(display_makes[:5]):
                img_url = get_car_image_url(make)
                img_cols[idx % 5].image(
                    img_url, 
                    caption=f"{make} Sample", 
                    use_container_width=True
                )
            st.markdown("---")


# -----------------------------
# INVENTORY TAB
# -----------------------------
with main_tabs[2]:
    st.markdown("### 📈 Your Inventory")
    try:
        # get_user_inventory handles fetching, cleaning, and parsing of data
        df_inventory = get_user_inventory(user_email)
        
        if df_inventory.empty:
            st.info("No listings for your account yet. Generate listings to populate this view.")
        else:
            # Show the raw/cleaned dataframe
            st.dataframe(df_inventory)
            
            # Display detailed view below
            st.markdown("#### Detailed Listing View")
            for idx, row in df_inventory.iterrows():
                st.subheader(f"{row.get('Year','')} {row.get('Make','')} {row.get('Model','')}")
                if row.get("Image_Link"):
                    st.image(row["Image_Link"], width=300)
                
                details = {k: row.get(k,"-") for k in ["Mileage","Color","Fuel","Transmission","Price","Features","Notes"]}
                st.table(pd.DataFrame(details.items(), columns=["Attribute","Value"]))
                
                st.markdown("#### Listing Description")
                st.write(row.get("Listing","No description found."))
                st.markdown("---")
                
            st.download_button(
                "⬇ Download Inventory CSV",
                df_inventory.to_csv(index=False).encode("utf-8"),
                file_name="dealer_inventory.csv",
                mime="text/csv"
            )

    except Exception as e:
        st.error(f"⚠️ Error loading inventory: {e}")