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
from backend.sheet_utils import append_to_google_sheet, get_sheet_data, get_inventory_for_user # Keep get_inventory_for_user
from backend.platinum_manager import (
    can_add_listing,
    increment_platinum_usage,
)

# NOTE: Removed unused imports like check_listing_limit, has_feature, create_checkout_session, etc., for cleanliness.

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


# ---------------------------------------------------------
# HELPER FUNCTIONS (Including the missing get_user_inventory)
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
        # Use the imported function to fetch data
        df = pd.DataFrame(get_inventory_for_user(email))
        
        if df.empty:
            return pd.DataFrame(columns=["Make", "Model", "Year", "Price", "Mileage", "Timestamp"])
        
        df.columns = [str(c).strip() for c in df.columns]

        # Standardize timestamp parsing
        timestamp_col = next((c for c in df.columns if c.lower() in ["timestamp", "created", "created_at"]), None)
        if timestamp_col:
            df["Timestamp_parsed"] = pd.to_datetime(df[timestamp_col], errors="coerce")
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
        st.info(f"No data to display for '{title}'.")
        return

    # Check and convert columns to numeric if needed
    for col in [x, y, size]:
        if col and col in df.columns and not pd.api.types.is_numeric_dtype(df[col]):
            df[col] = pd.to_numeric(df[col], errors='coerce')

    try:
        chart_type = chart_type.lower()
        if chart_type == "line":
            fig = px.line(df, x=x, y=y, color=color, markers=True, title=title)
        elif chart_type == "bar":
            fig = px.bar(df, x=x, y=y, color=color, title=title)
        elif chart_type == "scatter":
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


def render_dashboard(df, title_prefix="Inventory"):
    """Render core analytics charts for real inventory or demo data."""
    if df.empty:
        st.info(f"No data available for {title_prefix}.")
        return

    st.markdown(f"### 📊 {title_prefix} Dashboard")

    # KPIs
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Cars", len(df))
    col2.metric("Average Price", f"£{int(df['Price_num'].mean()):,}" if "Price_num" in df.columns else "-")
    col3.metric("Average Mileage", f"{int(df['Mileage_num'].mean()):,} miles" if "Mileage_num" in df.columns else "-")

    # Time-based reports
    weekly_df, monthly_df = weekly_monthly_reports(df)
    plotly_chart(weekly_df, "line", x="Week", y="Listings", title=f"{title_prefix}: Listings Per Week")
    plotly_chart(monthly_df, "bar", x="Month", y="Listings", title=f"{title_prefix}: Listings Per Month")

    # Price histogram
    if "Price_num" in df.columns: 
        plotly_chart(df, "hist", x="Price_num", title=f"{title_prefix}: Price Distribution")
    
    # Mileage vs Price scatter
    if "Mileage_num" in df.columns and "Price_num" in df.columns:
        plotly_chart(df, "scatter", x="Mileage_num", y="Price_num", color="Make", hover=["Model","Year"], title=f"{title_prefix}: Mileage vs Price")
    
    # Make pie chart
    if "Make" in df.columns:
        make_counts = df["Make"].value_counts().reset_index()
        make_counts.columns = ["Make","Count"]
        plotly_chart(make_counts, "pie", x="Make", y="Count", title=f"{title_prefix}: Inventory by Make")


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
                
                # Using append_to_google_sheet which works with the new Sheet ID
                if append_to_google_sheet("Inventory", inventory_data):
                    st.success("✅ Listing saved!")
                    # This calls decrement_listing_count which updates the usage in User_Activity tab
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

    # Filter widgets 
    all_makes = ["All", "BMW", "Audi", "Mercedes", "Tesla", "Jaguar", "Land Rover", "Porsche"]
    all_models = ["All", "X5 M Sport", "Q7", "GLE", "Q8", "X6", "GLC", "GLE Coupe", "X3 M", "Q5", "Model X", "iX", "e-tron", "F-Pace", "Discovery", "X4", "Cayenne", "M3", "RS7", "C63 AMG", "S-Class", "7 Series", "A8"]
    
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        selected_make = st.selectbox("Filter by Make", all_makes, key="dash_make_filter")
    with filter_col2:
        selected_model = st.selectbox("Filter by Model", all_models, key="dash_model_filter")
        
    dashboard_type = st.selectbox("Select Data Source", ["Real Inventory", "Demo Data", "Demo Dashboards"])

    if dashboard_type == "Real Inventory":
        df = get_user_inventory(user_email)
        render_dashboard(df, title_prefix="Inventory")
        
    elif dashboard_type == "Demo Data":
        # NOTE: Simple demo data generator used here
        def generate_demo_data(seed=42):
            random.seed(seed)
            makes = ["BMW", "Audi", "Mercedes", "Tesla", "Porsche"]
            models = ["X5", "Q7", "GLE", "Model S", "Cayenne"]
            data = []
            for _ in range(50):
                make = random.choice(makes)
                data.append({
                    "Make": make, 
                    "Model": random.choice(models), 
                    "Year": random.randint(2018, 2023),
                    "Price_num": random.randint(40000, 90000),
                    "Mileage_num": random.randint(5000, 50000),
                    "Timestamp_parsed": datetime.utcnow() - timedelta(days=random.randint(1, 365))
                })
            return pd.DataFrame(data)

        df = generate_demo_data(seed=st.number_input("Demo Seed", value=42, step=1, key="demo_seed_input"))
        render_dashboard(df, title_prefix="Demo")

    elif dashboard_type == "Demo Dashboards":
        # Generate and show individual demo dashboards (as previously intended)
        
        # ----- Demo Data for 8 Dashboards (simplified) -----
        demo_data = [
            {"top_recs": [{"Year": "2021", "Make": "BMW", "Model": "X5 M Sport", "Score": 88}]},
            {"top_recs": [{"Year": "2022", "Make": "Audi", "Model": "Q8", "Score": 87}]},
            {"top_recs": [{"Year": "2020", "Make": "Mercedes", "Model": "GLE Coupe", "Score": 85}]},
            {"top_recs": [{"Year": "2021", "Make": "Tesla", "Model": "Model X", "Score": 90}]},
            {"top_recs": [{"Year": "2021", "Make": "Jaguar", "Model": "F-Pace", "Score": 82}]},
            {"top_recs": [{"Year": "2022", "Make": "Porsche", "Model": "Cayenne", "Score": 88}]},
            {"top_recs": [{"Year": "2021", "Make": "BMW", "Model": "M3", "Score": 86}]},
            {"top_recs": [{"Year": "2022", "Make": "Mercedes", "Model": "S-Class", "Score": 92}]}
        ]
        
        for i, data in enumerate(demo_data, start=1):
            top_recs_df = pd.DataFrame(data["top_recs"])
            
            st.markdown(f"## Demo Dashboard {i}")
            
            # Top Recommendation Images (3 columns; dynamic)
            st.markdown("**🚗 Sample Car Images**")
            cols = st.columns(3)
            for idx, row in top_recs_df.iterrows():
                img_url = get_car_image_url(row["Make"])
                col = cols[idx % 3]
                col.image(img_url, caption=f"{row['Year']} {row['Make']} {row['Model']}", use_container_width=True)

            # --- Additional Charts (Stub) ---
            st.info("Additional charts for social, inventory, and content calendar would go here.")
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