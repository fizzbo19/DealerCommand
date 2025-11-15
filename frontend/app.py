# frontend/app.py
import sys, os, io, json
from datetime import datetime
import streamlit as st
import pandas as pd
from openai import OpenAI

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
# GOOGLE DRIVE SETUP (GRACEFUL FAIL)
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
expiry_date = profile.get("Trial_Expiry")
usage_count = profile.get("Usage_Count", 0)
remaining_listings = profile.get("Remaining_Listings", 15)
is_active = status in ["active", "new"]
remaining_days = max((expiry_date - datetime.utcnow()).days, 0) if expiry_date else 0

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
sidebar_tabs = st.sidebar.tabs(["🎯 Trial Overview", "💳 Upgrade Plans", "⚙️ User Settings"])
with sidebar_tabs[0]:
    st.markdown("### 🎯 Your DealerCommand Trial")
    st.markdown(f"**👤 Email:** `{user_email}`")
    st.markdown(f"**📊 Listings Used:** `{usage_count}` / 15")
    st.progress(int(min((usage_count / 15) * 100, 100)))
    st.markdown(f"**🟢 Status:** Active Trial" if is_active else "**🔴 Status:** Expired Trial")
    st.markdown(f"**⏳ Days Remaining:** `{remaining_days}` days")
    st.markdown(f"**📌 Remaining Listings:** `{remaining_listings}`")

if plan in ["pro", "platinum"]:
    st.sidebar.markdown("### 👥 Manage Users")
    with st.sidebar.expander("Add Team Member"):
        new_user_email = st.text_input("Team Member Email")
        if st.button("Add User"):
            if can_user_login(new_user_email, plan):
                append_to_google_sheet("Dealership_Profiles", {
                    "Email": new_user_email,
                    "Plan": plan,
                    "Joined_On": datetime.utcnow().isoformat()
                })
                st.success(f"✅ {new_user_email} added to {plan.capitalize()} plan.")
            else:
                st.warning(f"🚫 Cannot add {new_user_email}. Seat limit reached.")

# ---------------------------------------------------------
# MAIN TABS
# ---------------------------------------------------------
main_tabs = st.tabs(["🧾 Generate Listing", "📊 Analytics Dashboard", "📈 Inventory"])

# ----------------
# GENERATE LISTING
# ----------------
with main_tabs[0]:
    if is_active and (remaining_listings > 0 or is_platinum(user_email)):
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
                st.warning("⚠️ You have reached your listing limit. Upgrade to Platinum to add unlimited listings.")
            else:
                try:
                    client = OpenAI(api_key=api_key)
                    prompt = f"""
Write a 120–150 word engaging car listing:
{year} {make} {model}, {mileage}, {color}, {fuel}, {transmission}, {price}.
Features: {features}. Dealer Notes: {notes}.
Include emojis and SEO-rich phrasing.
"""
                    with st.spinner("🤖 Generating your listing..."):
                        response = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {"role":"system","content":"You are a top-tier automotive copywriter."},
                                {"role":"user","content":prompt}
                            ],
                            temperature=0.7
                        )
                    listing_text = response.choices[0].message.content.strip() if response and getattr(response, "choices", None) else ""
                    st.success("✅ Listing generated successfully!")
                    st.markdown(f"**Generated Listing:**\n\n{listing_text}")
                    st.download_button("⬇ Download Listing", listing_text, file_name="listing.txt")

                    # Upload image if provided
                    image_link = None
                    if car_image:
                        image_link = upload_image_to_drive(car_image, f"{make}_{model}_{datetime.utcnow().isoformat()}.png")
                        if not image_link:
                            st.warning("⚠️ Failed to upload image. Listing will be saved without image.")

                    # Save inventory
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
                        "Image_Link": image_link if image_link else ""
                    }

                    saved = append_to_google_sheet("Inventory", inventory_data)
                    if saved:
                        st.success("✅ Listing saved successfully!")
                        increment_platinum_usage(user_email, 1)
                    else:
                        st.error("⚠️ Failed to save listing.")
                except Exception as e:
                    st.error(f"⚠️ Unexpected error: {e}")
    else:
        st.warning("⚠️ Your trial has ended or listing limit reached. Please upgrade to continue.")

# ----------------
# ANALYTICS DASHBOARD
# ----------------
with main_tabs[1]:
    st.markdown("### 📊 Analytics Dashboard")
    if is_platinum(user_email):
        dashboard = get_platinum_dashboard(user_email)
        # Profile Info
        st.markdown(f"**👤 Email:** {dashboard['Profile']['Email']}")
        st.markdown(f"**Plan:** {dashboard['Profile']['Plan']}")
        st.markdown(f"**Inventory Count:** {dashboard['Inventory_Count']}")
        st.markdown(f"**Remaining Listings:** {dashboard['Remaining_Listings']}")

        # Top Recommendations
        st.markdown("#### 🌟 Top Recommended Listings")
        top_df = pd.DataFrame(dashboard["Top_Recommendations"])
        if not top_df.empty:
            st.dataframe(top_df)
        else:
            st.info("No recommendations available yet.")

        # Social Media Insights
        st.markdown("#### 📱 Social Media Insights")
        social_df = pd.DataFrame(dashboard["Social_Data"])
        if not social_df.empty:
            st.dataframe(social_df)
        else:
            st.info("No social media data yet.")

        # AI Video Script Generator
        st.markdown("### 🎬 AI Video Script Generator")
        inventory_df = get_inventory_for_user(user_email)
        listing_options = []
        if not top_df.empty:
            for _, row in top_df.iterrows():
                listing_options.append(f"{row['Year']} {row['Make']} {row['Model']} (Top Recommendation)")
        if not inventory_df.empty:
            for _, row in inventory_df.iterrows():
                listing_options.append(f"{row['Year']} {row['Make']} {row['Model']}")
        if listing_options:
            selected_listing_name = st.selectbox("Select a listing for AI video script", listing_options)
            if st.button("Generate Video Script"):
                if "(Top Recommendation)" in selected_listing_name:
                    idx = listing_options.index(selected_listing_name)
                    selected_listing = top_df.iloc[idx].to_dict()
                else:
                    idx = listing_options.index(selected_listing_name) - len(top_df)
                    selected_listing = inventory_df.iloc[idx].to_dict()
                with st.spinner("🤖 Generating video script..."):
                    script = generate_ai_video_script(user_email, selected_listing)
                st.success("✅ Video script generated!")
                st.text_area("🎬 Generated Script", script, height=250)
                st.download_button("⬇ Download Video Script", script, file_name=f"{selected_listing['Make']}_{selected_listing['Model']}_script.txt")

        # Competitor Monitoring
        st.markdown("### 🏁 Competitor Monitoring")
        competitor_file = st.file_uploader("Upload Competitor CSV", type=["csv"])
        sheet_input = st.text_input("Or enter Google Sheet name for competitor data")
        if st.button("Analyze Competitors"):
            if not competitor_file and not sheet_input:
                st.warning("⚠️ Provide either a CSV or a Sheet name to analyze competitors.")
            else:
                comp_df, comp_summary = competitor_monitoring(user_email, competitor_csv=competitor_file, sheet_name=sheet_input)
                if comp_df.empty:
                    st.info(comp_summary)
                else:
                    st.success(f"✅ Found {comp_summary['Total_Competitors']} competitor listings")
                    st.markdown(f"**Average Price:** £{comp_summary['Avg_Price']}")
                    st.markdown(f"**Lowest Price:** £{comp_summary['Min_Price']}")
                    st.markdown(f"**Highest Price:** £{comp_summary['Max_Price']}")
                    st.markdown(f"**Most Common Make:** {comp_summary['Most_Common_Make']}")
                    st.markdown(f"**Most Common Model:** {comp_summary['Most_Common_Model']}")
                    st.dataframe(comp_df.head(20))
                    st.download_button("⬇ Download Competitor Data", comp_df.to_csv(index=False), file_name="competitor_data.csv")

        # Weekly Content Calendar
        st.markdown("### 📅 Weekly Content Calendar")
        if st.button("Generate Weekly Calendar"):
            calendar_df, message = generate_weekly_content_calendar(user_email, plan="platinum")
            if calendar_df.empty:
                st.warning(message)
            else:
                st.success(message)
                st.dataframe(calendar_df)
                st.download_button(
                    "⬇ Download Content Calendar",
                    calendar_df.to_csv(index=False),
                    file_name="weekly_content_calendar.csv"
                )

    else:
        analytics = analytics_dashboard(user_email, plan=plan)
        for key, value in analytics.items():
            if key.startswith("chart_") and value is not None:
                st.markdown(f"#### {key.replace('chart_', '').replace('_',' ').title()}")
                st.image(value)
            elif isinstance(value, dict):
                st.markdown(f"#### {key.replace('_',' ').title()}")
                st.table(pd.DataFrame(value.items(), columns=["Metric", "Value"]))
            else:
                st.markdown(f"**{key.replace('_',' ').title()}:** {value}")

        if plan == "free":
            st.info("Upgrade to Pro or Platinum to view full analytics and charts. Start a 30-day trial to preview Platinum features.")

# ----------------
# INVENTORY TAB
# ----------------
with main_tabs[2]:
    st.markdown("### 📈 Your Inventory")
    try:
        df_inventory = get_sheet_data("Inventory")
        if df_inventory is None or df_inventory.empty:
            st.info("No inventory has been added yet.")
            st.stop()

        df_inventory.columns = [str(c).strip() for c in df_inventory.columns]
        possible_email_columns = ["Email","email","E-mail","e-mail","User","user_email"]
        email_col = next((c for c in df_inventory.columns if c in possible_email_columns), None)
        if not email_col:
            st.error("⚠️ Inventory sheet missing an 'Email' column. Please add one.")
            st.stop()

        df_inventory[email_col] = df_inventory[email_col].astype(str).str.lower()
        filtered = df_inventory[df_inventory[email_col] == user_email.lower()]

        if filtered.empty:
            st.info("You haven't added any listings yet.")
            st.stop()

        top_recommended_ids = []
        if is_platinum(user_email):
            platinum_dashboard = get_platinum_dashboard(user_email)
            top_df = pd.DataFrame(platinum_dashboard["Top_Recommendations"])
            if not top_df.empty and "Inventory_ID" in top_df.columns:
                top_recommended_ids = top_df["Inventory_ID"].tolist()

        for idx, row in filtered.iterrows():
            listing_title = f"{row.get('Year','')} {row.get('Make','')} {row.get('Model','')}"
            if row.get("Inventory_ID") in top_recommended_ids:
                listing_title += " 🌟 Top Recommendation"

            st.subheader(listing_title)
            if row.get("Image_Link"):
                st.image(row["Image_Link"], width=300)

            details = {k: row.get(k,"-") for k in ["Mileage","Color","Fuel","Transmission","Price","Features","Notes"]}
            st.table(pd.DataFrame(details.items(), columns=["Attribute","Value"]))
            st.markdown("#### Listing Description")
            st.write(row.get("Listing","No description found."))
            st.markdown("---")

        # Platinum AI Social Media Suggestions
        if is_platinum(user_email) and top_recommended_ids:
            st.markdown("### 📱 AI Social Media Post Suggestions")
            for inv_id in top_recommended_ids:
                listing_row = filtered[filtered["Inventory_ID"] == inv_id].iloc[0]
                listing_title = f"{listing_row.get('Year','')} {listing_row.get('Make','')} {listing_row.get('Model','')}"
                st.markdown(f"**{listing_title}**")
                st.write("💡 Suggested AI caption for Instagram/TikTok:")
                st.text_area("Caption", f"Check out this amazing {listing_title} now available at our dealership!", height=100)

    except Exception as e:
        st.error(f"⚠️ Error loading inventory: {e}")
