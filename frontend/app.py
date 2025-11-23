# frontend/app.py
import sys
import os
import io
import json
import random
import zipfile
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import plotly.express as px
from openai import OpenAI

# ---------------------------------------------------------
# PATH SETUP (assumes frontend/app.py inside frontend/)
# ---------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.extend([BASE_DIR, BACKEND_DIR])

# ---------------------------------------------------------
# LOCAL IMPORTS (backend modules you provided)
# ---------------------------------------------------------
from backend.trial_manager import (
    get_dealership_status,
    check_listing_limit,
    increment_usage,
    can_user_login
)
from backend.sheet_utils import append_to_google_sheet, get_sheet_data
from backend.platinum_manager import (
    can_add_listing,
    increment_platinum_usage,
    get_platinum_remaining_listings
)
from backend.analytics import (
    render_charts_for_streamlit,
    pro_analytics,
    generate_demo_data,
)
# ---------------------------------------------------------
# GOOGLE DRIVE SETUP (optional)
# ---------------------------------------------------------
try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    GOOGLE_API_AVAILABLE = True
except Exception:
    GOOGLE_API_AVAILABLE = False

def upload_image_to_drive(file_obj, filename, folder_id=None):
    """
    Uploads a file-like object to Google Drive and returns a shareable view URL.
    Returns None on failure or if Drive is not available.
    """
    if file_obj is None:
        return None
    if not GOOGLE_API_AVAILABLE:
        # fallback: store locally to /tmp and return path (useful for local testing)
        local_dir = "/tmp/dealercommand_uploads"
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, filename)
        try:
            with open(local_path, "wb") as f:
                file_obj.seek(0)
                f.write(file_obj.read())
            return local_path
        except Exception:
            return None

    try:
        raw = os.environ.get("GOOGLE_CREDENTIALS_JSON") or os.environ.get("GOOGLE_CREDENTIALS")
        if not raw:
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
        # make public readable
        service.permissions().create(fileId=file_id, body={"role": "reader", "type": "anyone"}).execute()
        return f"https://drive.google.com/uc?id={file_id}"
    except Exception as e:
        print("Drive upload failed:", e)
        return None

# ---------------------------------------------------------
# STREAMLIT PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(page_title="DealerCommand AI | Smart Listings", layout="wide", page_icon="🚗")
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
LOGO_FILE = os.path.join(ASSETS_DIR, "dealercommand_logov1.png")
if os.path.exists(LOGO_FILE):
    st.sidebar.image(LOGO_FILE, width=160)
else:
    st.sidebar.markdown("**DealerCommand AI**")

st.markdown('<h2 style="text-align:center;">🚗 DealerCommand AI</h2>', unsafe_allow_html=True)
st.markdown('<div class="hero-sub">Create high-converting, SEO-optimised car listings in seconds with AI.</div>', unsafe_allow_html=True)

# ---------------------------------------------------------
# OPENAI CLIENT
# ---------------------------------------------------------
API_KEY = os.environ.get("OPENAI_API_KEY")
if not API_KEY:
    st.error("⚠️ Missing OPENAI_API_KEY environment variable.")
    st.stop()
client = OpenAI(api_key=API_KEY)

def openai_generate(prompt, model="gpt-4o-mini", temperature=0.6, max_tokens=250):
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role":"system","content":"You are an expert automotive analyst and copywriter."},
                {"role":"user","content":prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )
        if resp and getattr(resp, "choices", None):
            return resp.choices[0].message.content.strip()
        return ""
    except Exception as e:
        print("OpenAI error:", e)
        return f"⚠️ OpenAI error: {e}"

# ---------------------------------------------------------
# DEALERSHIP LOGIN / TRIAL
# ---------------------------------------------------------
user_email = st.text_input("📧 Dealership email", placeholder="e.g. sales@autohub.co.uk")
if not user_email:
    st.info("👋 Enter your dealership email above to start your 30-day free trial.")
    st.stop()

# get profile & trial info from backend/trial_manager
profile = get_dealership_status(user_email)
plan = profile.get("Plan", "free").lower()
status = profile.get("Trial_Status", "new")
usage_count = int(profile.get("Usage_Count", 0) or 0)
remaining_listings = int(profile.get("Remaining_Listings", 15) or 15)
trial_expiry = profile.get("Trial_Expiry")  # expected as datetime or None

# compute trial days left
if isinstance(trial_expiry, datetime):
    delta = trial_expiry - datetime.utcnow()
    trial_days_left = max(0, delta.days)
    is_trial_active = delta.total_seconds() > 0
else:
    trial_days_left = 30
    is_trial_active = True if status in ("new","active") else False

current_plan = "platinum" if is_trial_active else plan

if not can_user_login(user_email, plan):
    st.error(f"🚫 Seat limit reached for {plan.capitalize()} plan.")
    st.stop()

# first-time onboarding
if status == "new":
    st.info("👋 Welcome! Please provide your dealership info to start your trial.")
    with st.form("dealer_info_form"):
        dealer_name = st.text_input("Dealership Name")
        dealer_phone = st.text_input("Phone Number")
        dealer_location = st.text_input("Location / City")
        submitted = st.form_submit_button("Save Info")
        if submitted:
            # call backend save - keep minimal here (sheet_utils.save_dealership_profile)
            try:
                from backend.sheet_utils import save_dealership_profile
                save_dealership_profile(user_email, {
                    "Name": dealer_name,
                    "Phone": dealer_phone,
                    "Location": dealer_location,
                    "Plan": plan
                })
                st.success("✅ Dealership info saved!")
            except Exception as e:
                st.error(f"⚠️ Failed to save dealership info: {e}")

# Sidebar: plans + overview
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
st.sidebar.markdown(f"**📊 Listings Used:** `{usage_count}` / {remaining_listings if not is_trial_active else 'unlimited (trial)'}")
st.sidebar.progress(int(min((usage_count / 15) * 100, 100)))
st.sidebar.markdown(f"**🟢 Status:** {'Trial Active' if is_trial_active else 'Trial Ended'}")
st.sidebar.markdown(f"**⏳ Trial Days Remaining:** `{trial_days_left}`" if is_trial_active else "")

# ---------------------------------------------------------
# MAIN UI TABS
# ---------------------------------------------------------
main_tabs = st.tabs(["🧾 Generate Listing", "📊 Analytics Dashboard", "📈 Inventory"])

# ----------------
# GENERATE LISTING
# ----------------
with main_tabs[0]:
    allowed = (is_trial_active and current_plan == "platinum") or can_add_listing(user_email)
    if allowed:
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
            submit_listing = st.form_submit_button("✨ Generate Listing")

        if submit_listing:
            # generate listing text
            prompt = f"""
Write a 120–150 word engaging car listing:
{year} {make} {model}, {mileage}, {color}, {fuel}, {transmission}, {price}.
Features: {features}. Dealer Notes: {notes}.
Include emojis and SEO-rich phrasing and a short call-to-action.
"""
            with st.spinner("🤖 Generating listing..."):
                listing_text = openai_generate(prompt, temperature=0.7, max_tokens=300)

            st.success("✅ Listing generated!")
            st.text_area("Generated Listing", listing_text, height=250)
            st.download_button("⬇ Download Listing", listing_text, file_name=f"{make}_{model}_listing.txt")

            # Upload image (if provided)
            image_link = ""
            if car_image is not None:
                # convert streamlit UploadedFile to BytesIO for upload_image_to_drive
                try:
                    image_bytes = car_image.getvalue()
                    image_file_like = io.BytesIO(image_bytes)
                    filename = f"{user_email}_{make}_{model}_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.png"
                    uploaded = upload_image_to_drive(image_file_like, filename)
                    if uploaded:
                        image_link = uploaded
                    else:
                        st.warning("⚠️ Image not uploaded to Drive — saved locally or failed. Listing will still be saved.")
                except Exception as e:
                    st.warning(f"⚠️ Image processing failed: {e}")

            # prepare inventory record
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

            # append to Google Sheets via sheet_utils.append_to_google_sheet
            saved = False
            try:
                saved = append_to_google_sheet("Inventory", inventory_data)
            except Exception as e:
                st.error(f"⚠️ Exception saving listing: {e}")
                saved = False

            if saved:
                st.success("✅ Listing saved to Inventory!")
                # increment usage: if trial => increment platinum usage method, else normal increment
                try:
                    if is_trial_active:
                        # if your platinum manager function expects different name, adjust
                        increment_platinum_usage(user_email, 1)
                    else:
                        increment_usage(user_email, num=1)
                except Exception:
                    # best-effort: ignore increment failure but log in console
                    print("Warning: failed to increment usage.")
            else:
                st.error("⚠️ Failed to save listing. Ensure sheet is accessible and correct columns exist.")
    else:
        st.warning("⚠️ Trial ended or listing limit reached. Upgrade to continue.")

# ----------------
# ANALYTICS DASHBOARD
# ----------------
with main_tabs[1]:
    st.markdown("### 📊 Analytics Dashboard")

    # CSV upload for dealer analytics (preferred)
    dealer_csv = st.file_uploader(
        "Upload your inventory CSV (optional) — will generate a custom dashboard",
        type=["csv"],
        key="dealer_inventory_upload"
    )

    # quick helper to request AI insight
    def ai_insight_for_chart(chart_name, sample_records):
        sample_text = json.dumps(sample_records, default=str)[:1500]  # truncated
        prompt = f"You are an automotive analytics assistant. Here is sample inventory data: {sample_text}\nGive a one-sentence insight about '{chart_name}' and one actionable suggestion (one sentence)."
        return openai_generate(prompt, temperature=0.45, max_tokens=150)

    # if dealer CSV is uploaded, use it as main analytics data
    if dealer_csv is not None:
        try:
            dealer_df = pd.read_csv(dealer_csv)
            st.success("✅ Dealer inventory loaded. Generating analytics...")

            # ensure numeric Price/Mileage columns
            if "Price" in dealer_df.columns:
                dealer_df["Price_numeric"] = pd.to_numeric(dealer_df["Price"].replace('£','',regex=True).replace(',','',regex=True), errors='coerce')
            else:
                dealer_df["Price_numeric"] = pd.NA

            if "Mileage" in dealer_df.columns:
                # handle formats like '28,000 miles'
                try:
                    dealer_df["Mileage_numeric"] = dealer_df["Mileage"].astype(str).str.replace(" miles","", regex=False).str.replace(",","", regex=False)
                    dealer_df["Mileage_numeric"] = pd.to_numeric(dealer_df["Mileage_numeric"], errors='coerce')
                except Exception:
                    dealer_df["Mileage_numeric"] = pd.NA
            else:
                dealer_df["Mileage_numeric"] = pd.NA

            # Standard KPIs
            st.markdown("#### Dealer Inventory Summary")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Cars", len(dealer_df))
            c2.metric("Avg Price", f"£{int(dealer_df['Price_numeric'].mean()):,}" if not dealer_df["Price_numeric"].isna().all() else "£0")
            c3.metric("Avg Mileage", f"{int(dealer_df['Mileage_numeric'].mean()):,} miles" if not dealer_df["Mileage_numeric"].isna().all() else "-")
            most_common_make = dealer_df['Make'].mode()[0] if "Make" in dealer_df.columns and not dealer_df['Make'].dropna().empty else "-"
            c4.metric("Top Make", most_common_make)

            # Price distribution
            if "Price_numeric" in dealer_df.columns and not dealer_df["Price_numeric"].isna().all():
                st.markdown("#### Price Distribution")
                fig_price = px.histogram(dealer_df, x="Price_numeric", nbins=20, title="Price Distribution")
                st.plotly_chart(fig_price, use_container_width=True)
                st.info(f"💡 AI Insight: {ai_insight_for_chart('Price Distribution', dealer_df.head(10).to_dict(orient='records'))}")

            # Mileage vs Price
            if "Mileage_numeric" in dealer_df.columns and "Price_numeric" in dealer_df.columns:
                st.markdown("#### Mileage vs Price")
                fig_scatter = px.scatter(dealer_df, x="Mileage_numeric", y="Price_numeric",
                                        color="Make" if "Make" in dealer_df.columns else None,
                                        hover_data=["Model","Year"] if "Model" in dealer_df.columns and "Year" in dealer_df.columns else None,
                                        title="Mileage vs Price")
                st.plotly_chart(fig_scatter, use_container_width=True)
                st.info(f"💡 AI Insight: {ai_insight_for_chart('Mileage vs Price', dealer_df.head(10).to_dict(orient='records'))}")

            # Listings over time if Timestamp present
            if "Timestamp" in dealer_df.columns:
                try:
                    dealer_df["Timestamp"] = pd.to_datetime(dealer_df["Timestamp"], errors="coerce")
                    dealer_df["Date"] = dealer_df["Timestamp"].dt.date
                    trends = dealer_df.groupby("Date").size().reset_index(name="Listings")
                    st.markdown("#### Listings Over Time")
                    fig_trends = px.line(trends, x="Date", y="Listings", title="Listings Added Over Time", markers=True)
                    st.plotly_chart(fig_trends, use_container_width=True)
                    st.info(f"💡 AI Insight: {ai_insight_for_chart('Listings Over Time', dealer_df.head(10).to_dict(orient='records'))}")
                except Exception:
                    pass

            # Inventory by Make
            if "Make" in dealer_df.columns:
                st.markdown("#### Inventory by Make")
                make_counts = dealer_df["Make"].value_counts().reset_index()
                make_counts.columns = ["Make", "Count"]
                fig_make = px.pie(make_counts, names="Make", values="Count", title="Inventory by Make")
                st.plotly_chart(fig_make, use_container_width=True)
                st.info(f"💡 AI Insight: {ai_insight_for_chart('Inventory by Make', dealer_df.head(10).to_dict(orient='records'))}")

            # Top models table
            if "Model" in dealer_df.columns and "Price_numeric" in dealer_df.columns:
                st.markdown("#### Top Models by Average Price")
                top_models = dealer_df.groupby("Model")["Price_numeric"].mean().reset_index().sort_values("Price_numeric", ascending=False).head(10)
                st.dataframe(top_models)
                st.info(f"💡 AI Insight: {ai_insight_for_chart('Top Models', dealer_df.head(10).to_dict(orient='records'))}")

        except Exception as e:
            st.error(f"⚠️ Failed to read uploaded CSV: {e}")
    else:
        # No CSV uploaded - try to generate analytics from user's inventory sheet if available
        try:
            sheet_df = get_sheet_data("Inventory")
            if sheet_df is None or sheet_df.empty:
                st.info("No inventory found in the connected sheet. Upload a CSV to see analytics demo.")
                # show small demo sample
                demo_df = generate_demo_data()
                st.markdown("#### Demo Analytics (no dealer data found)")
                fig_demo = px.line(demo_df.groupby(demo_df['Date'].dt.to_period('M'))['Revenue'].sum().reset_index(), x="Date", y="Revenue", title="Demo Revenue Over Time")
                st.plotly_chart(fig_demo, use_container_width=True)
            else:
                # filter to user's email
                email_col = next((c for c in sheet_df.columns if str(c).lower() == "email"), None)
                if email_col:
                    user_df = sheet_df[sheet_df[email_col].astype(str).str.lower() == user_email.lower()].copy()
                else:
                    user_df = sheet_df.copy()

                if user_df.empty:
                    st.info("No listings for your account yet (in the Inventory sheet). Upload CSV if you want to preview analytics.")
                else:
                    # reuse some of the dealer_csv rendering logic for user_df
                    # ensure numeric conversions
                    if "Price" in user_df.columns:
                        user_df["Price_numeric"] = pd.to_numeric(user_df["Price"].replace('£','',regex=True).replace(',','',regex=True), errors='coerce')
                    if "Mileage" in user_df.columns:
                        user_df["Mileage_numeric"] = pd.to_numeric(user_df["Mileage"].astype(str).str.replace(" miles","",regex=False).str.replace(",","",regex=False), errors='coerce')

                    st.markdown("#### Your Inventory Summary")
                    a1, a2, a3, a4 = st.columns(4)
                    a1.metric("Total Cars", len(user_df))
                    a2.metric("Avg Price", f"£{int(user_df['Price_numeric'].mean()):,}" if "Price_numeric" in user_df.columns and not user_df['Price_numeric'].isna().all() else "£0")
                    a3.metric("Avg Mileage", f"{int(user_df['Mileage_numeric'].mean()):,} miles" if "Mileage_numeric" in user_df.columns and not user_df['Mileage_numeric'].isna().all() else "-")
                    a4.metric("Top Make", user_df['Make'].mode()[0] if "Make" in user_df.columns and not user_df['Make'].dropna().empty else "-")

                    # Revenue over time (if Timestamp exists and prices)
                    if "Timestamp" in user_df.columns and "Price_numeric" in user_df.columns:
                        try:
                            user_df["Timestamp"] = pd.to_datetime(user_df["Timestamp"], errors="coerce")
                            user_df["Date"] = user_df["Timestamp"].dt.date
                            rev = user_df.groupby("Date")["Price_numeric"].sum().reset_index()
                            fig_rev = px.line(rev, x="Date", y="Price_numeric", title="Revenue Over Time", markers=True)
                            st.plotly_chart(fig_rev, use_container_width=True)
                            st.info(f"💡 AI Insight: {ai_insight_for_chart('Revenue Over Time', user_df.head(10).to_dict(orient='records'))}")
                        except Exception:
                            pass

                    # Price distribution
                    if "Price_numeric" in user_df.columns and not user_df["Price_numeric"].isna().all():
                        fig_price_user = px.histogram(user_df, x="Price_numeric", nbins=20, title="Price Distribution")
                        st.plotly_chart(fig_price_user, use_container_width=True)
                        st.info(f"💡 AI Insight: {ai_insight_for_chart('Price Distribution', user_df.head(10).to_dict(orient='records'))}")

        except Exception as e:
            st.error(f"⚠️ Error generating analytics: {e}")

    # -------- Demo dashboards at bottom (toggle)
    st.markdown("---")
    show_demo = st.checkbox("Show reference demo dashboards (5)", value=False)
    if show_demo:
        demo_data = generate_demo_data()  # returns a DataFrame for demo; we'll craft 5 visual examples
        # create 5 small demo variants by sampling
        demo_list = []
        for i in range(5):
            d = generate_demo_data()
            demo_list.append(d)

        for i, ddf in enumerate(demo_list, start=1):
            st.markdown(f"### Demo Dashboard {i}")
            # revenue
            rev = ddf.groupby(ddf['Date'].dt.to_period('M'))['Revenue'].sum().reset_index()
            rev['Date'] = pd.to_datetime(rev['Date'].astype(str))
            fig = px.line(rev, x="Date", y="Revenue", title=f"Demo Revenue Over Time {i}")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(ddf.head(6))
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
        else:
            # normalize columns and locate email column
            df_inventory.columns = [str(c).strip() for c in df_inventory.columns]
            email_col = next((c for c in df_inventory.columns if c.lower() == "email"), None)
            if not email_col:
                st.error("⚠️ Inventory sheet missing an 'Email' column.")
            else:
                df_inventory[email_col] = df_inventory[email_col].astype(str).str.lower()
                user_rows = df_inventory[df_inventory[email_col] == user_email.lower()]
                if user_rows.empty:
                    st.info("No listings for your account yet.")
                else:
                    for idx, row in user_rows.iterrows():
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

