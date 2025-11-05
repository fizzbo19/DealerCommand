# frontend/app.py
import os
import streamlit as st
import datetime
import json
from openai import OpenAI
import gspread
from pathlib import Path
import stripe
from google.oauth2.service_account import Credentials

# ---------- Config ----------
TRIAL_DURATION_DAYS = 90  # 90 days trial (3 months)
SHEET_URL = "https://docs.google.com/spreadsheets/d/12UDiRnjQXwxcHFjR3SWdz8lB45-OTGHBzm3YVcExnsQ/edit"

# ---------- Helpers: Google Sheets ----------
def get_sheet_safe():
    """Return sheet object or None if credentials/missing."""
    try:
        raw = os.environ.get("GOOGLE_CREDENTIALS_JSON")
        if not raw:
            return None
        credentials_info = json.loads(raw)
        creds = Credentials.from_service_account_info(credentials_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        client = gspread.authorize(creds)
        sheet = client.open_by_url(SHEET_URL).sheet1
        return sheet
    except Exception as e:
        # Do not crash the app on sheet errors
        st.warning("⚠️ Google Sheets not available: data will not persist. (Check GOOGLE_CREDENTIALS_JSON)")
        return None

def get_user_row(sheet, user_email):
    if not sheet:
        return None, None
    try:
        records = sheet.get_all_records()
        for i, r in enumerate(records, start=2):
            if str(r.get("Email", "")).lower() == user_email.lower():
                return i, r
    except Exception:
        return None, None
    return None, None

def save_user_usage(user_email, listing_text, tone=""):
    sheet = get_sheet_safe()
    if not sheet:
        return False
    row_idx, record = get_user_row(sheet, user_email)
    today = datetime.date.today()
    try:
        if record:
            new_count = int(record.get("Listings Generated", 0)) + 1
            sheet.update_cell(row_idx, 4, new_count)
        else:
            expiry_date = today + datetime.timedelta(days=TRIAL_DURATION_DAYS)
            sheet.append_row([user_email, str(today), str(expiry_date), 1])
        # store listing in "Listings History" worksheet
        ss = sheet.spreadsheet
        try:
            history = ss.worksheet("Listings History")
        except gspread.exceptions.WorksheetNotFound:
            history = ss.add_worksheet(title="Listings History", rows=2000, cols=6)
            history.append_row(["Email", "Date", "Car", "Price", "Tone", "Listing"])
        car_cell = f"{today.isoformat()} -"  # placeholder for Car column; we keep car in listing snippet
        history.append_row([user_email, str(today), "-", "-", tone, listing_text[:300]])
        return True
    except Exception:
        return False

def get_recent_listings(user_email, limit=10):
    sheet = get_sheet_safe()
    if not sheet:
        return []
    try:
        ss = sheet.spreadsheet
        try:
            history = ss.worksheet("Listings History")
        except gspread.exceptions.WorksheetNotFound:
            return []
        rows = history.get_all_records()
        # filter by user
        user_rows = [r for r in rows if str(r.get("Email","")).lower() == user_email.lower()]
        # latest first
        user_rows = user_rows[::-1][:limit]
        return user_rows
    except Exception:
        return []

def get_trial_status(user_email):
    sheet = get_sheet_safe()
    if not sheet:
        # if sheet unavailable, treat as active trial with 90 days left (safe fallback)
        return "active", (datetime.date.today() + datetime.timedelta(days=TRIAL_DURATION_DAYS)), 0
    _, record = get_user_row(sheet, user_email)
    if not record:
        return "new", None, 0
    try:
        expiry_date = datetime.datetime.strptime(record["Trial Ends"], "%Y-%m-%d").date()
    except Exception:
        expiry_date = datetime.date.today() + datetime.timedelta(days=TRIAL_DURATION_DAYS)
    used = int(record.get("Listings Generated", 0))
    if datetime.date.today() > expiry_date:
        return "expired", expiry_date, used
    return "active", expiry_date, used

# ---------- UI Styling (premium) ----------
st.set_page_config(page_title="DealerCommand AI", layout="wide")
st.markdown(
    """
    <style>
    /* Background */
    .reportview-container {
        background: linear-gradient(180deg,#0b0c10,#0f1116);
    }
    /* Card colors, fonts */
    .stApp { color: #E6EEF3; }
    .card { background-color: #0f1720; border-radius:12px; padding:16px; }
    h1, h2, h3 { color: #e6eef3; }
    .big-btn > button { background-color: #0066FF !important; color: white !important; border-radius:10px !important; padding: 10px 16px !important; }
    .small-btn > button { background-color: #2b2f40 !important; color: #e6eef3 !important; border-radius:8px !important; padding: 6px 10px !important; border: 1px solid #3b3f55 !important; }
    .stTextInput>div>div>input, .stTextArea>div>div>textarea, .stSelectbox>div>div>div {
        background-color: #0e1520 !important;
        color: #e6eef3 !important;
        border-radius:8px !important;
    }
    .metric { color: #cfe9ff !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Sidebar (status + quick actions) ----------
with st.sidebar:
    # Logo (safe loading)
    logo_path = Path(__file__).parent / "assets" / "dealercommand_logo.png"
    if logo_path.exists():
        st.image(str(logo_path), use_column_width=True)
    else:
        st.text("DealerCommand Logo not found")

    st.title("DealerCommand")
    st.caption("AI listings • Social captions • Analytics")
    email_sidebar = st.text_input("Your dealership email", key="sidebar_email")
    if email_sidebar:
        status, expiry, used = get_trial_status(email_sidebar)
        if status == "new":
            st.success("✨ 3-month free trial active from first use")
            st.info("You get full features for the trial")
        elif status == "active":
            days_left = (expiry - datetime.date.today()).days if expiry else TRIAL_DURATION_DAYS
            st.metric("Trial days left", f"{days_left}d")
            st.metric("Listings used", f"{used}")
        else:
            st.error("Trial expired")
            st.markdown("[Upgrade to Premium ➜](#pricing)")
    st.markdown("---")
    st.markdown("**Quick actions**")
    if st.button("Create a listing (main)"):
        st.experimental_rerun()
    st.markdown("Need help? Contact us at **hello@dealercommand.ai**")
    st.markdown("---")
    st.markdown("Version: 0.9 • Render")

# ---------- Main layout ----------
col_left, col_right = st.columns([2, 3])

with col_left:
    st.header("Generate a high-converting listing")
    st.markdown("Fill the details below and the AI will produce a persuasive listing and social caption.")
    with st.form("generate_form"):
        make = st.text_input("Make", "BMW")
        model = st.text_input("Model", "X5 M Sport")
        year = st.text_input("Year", "2021")
        mileage = st.text_input("Mileage", "28,000 miles")
        color = st.text_input("Colour", "Black")
        fuel = st.selectbox("Fuel Type", ["Petrol", "Diesel", "Hybrid", "Electric"])
        transmission = st.selectbox("Transmission", ["Automatic", "Manual"])
        price = st.text_input("Price", "£45,995")
        tone = st.selectbox("Tone / Style", ["Professional", "Sporty", "Luxury", "Casual"])
        features = st.text_area("Key features (comma separated)", "Panoramic roof, heated seats, M Sport package")
        notes = st.text_area("Dealer notes (optional)", "Full service history, finance available")
        submit = st.form_submit_button("Generate listing", help="Creates an AI listing + social caption")

    if submit:
        # Validate OpenAI and run
        openai_key = os.environ.get("OPENAI_API_KEY")
        if not openai_key:
            st.error("OpenAI key not configured. Set OPENAI_API_KEY in your Render environment variables.")
        else:
            client = OpenAI(api_key=openai_key)
            prompt = f"""
            You are an expert car sales assistant. Create a compelling, 100-150 word listing in separate paragraphs with emojis.
            Tone: {tone}
            Car: {year} {make} {model}
            Mileage: {mileage}
            Colour: {color}
            Fuel: {fuel}
            Transmission: {transmission}
            Price: {price}
            Features: {features}
            Dealer notes: {notes}
            """
            with st.spinner("Generating listing…"):
                try:
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role":"system", "content":"You are a helpful car sales assistant."},
                                  {"role":"user","content":prompt}],
                        temperature=0.8,
                    )
                    listing = response.choices[0].message.content
                except Exception as e:
                    st.error(f"AI error: {e}")
                    listing = None

            if listing:
                st.success("Listing generated — see right panel")
                # Save listing
                saved = save_user_usage(email_sidebar or "", listing, tone)
                if not saved:
                    st.info("Listing generated — storage skipped (Google Sheets unavailable).")

with col_right:
    st.header("Result & Tools")
    # Show generated listing if present
    # The listing variable is only defined in the left block when created; safe get via session_state
    listing_text = st.session_state.get("generated_listing") if "generated_listing" in st.session_state else None
    # After generation, set listing_text from local variable if present
    try:
        # if we just generated, listing is in locals()
        listing_text = listing if 'listing' in locals() else listing_text
    except Exception:
        listing_text = listing_text

    if listing_text:
        st.subheader("📋 AI-Generated Listing")
        st.markdown(listing_text)
        st.download_button("⬇ Download listing", listing_text, file_name="car_listing.txt")
        st.markdown("---")
        # Social caption
        st.subheader("📱 Suggested social caption")
        # generate caption call (re-use client if present)
        try:
            caption_prompt = f"Create a short, catchy Instagram/TikTok caption for this car: {make} {model}. Include relevant emojis and hashtags."
            caption_resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role":"user","content":caption_prompt}],
                temperature=0.9
            )
            caption_text = caption_resp.choices[0].message.content
            st.markdown(caption_text)
            st.download_button("⬇ Download caption", caption_text, file_name="social_caption.txt")
        except Exception as e:
            st.info("Caption generation skipped: " + str(e))

    else:
        st.info("No listing yet — fill the form on the left and press Generate.")

    st.markdown("---")
    st.subheader("Recent listings")
    recent = get_recent_listings(email_sidebar or "")
    if recent:
        for r in recent:
            with st.expander(f"{r.get('Date','')} • {r.get('Car','')}"):
                st.write("Tone:", r.get("Tone",""))
                st.write(r.get("Listing",""))
    else:
        st.write("No saved listings yet.")

# ---------- Pricing / Upgrade Section ----------
st.markdown("## Pricing & Plans", anchor="pricing")
st.write("Choose the right plan for your dealership. All prices are GBP per month.")

# Features for each tier
pro_features = [
    "Up to 15 listings / month",
    "AI-generated listings (100–150 words)",
    "Auto social captions (Instagram / TikTok)",
    "Save listings to cloud (Google Sheets)",
    "Basic analytics dashboard"
]

premium_features = pro_features + [
    "Unlimited listings",
    "Advanced analytics & CSV export",
    "Team accounts (2 seats)",
    "Priority support & onboarding",
    "Auto-post to social (coming soon)"
]

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Pro (Intro)")
    st.markdown("**£9.99 / month**")
    for f in pro_features:
        st.markdown(f"- ✅ {f}")
    if st.button("Upgrade to Pro (Test)", key="upgrade_pro"):
        url = None
        if email_sidebar:
            url = create_checkout_session("price_xxxxx_pro", email_sidebar)
        if url:
            st.markdown(f"[Proceed to Checkout]({url})")
        else:
            st.info("Checkout not configured — set Stripe keys & price IDs in environment.")

with col_b:
    st.subheader("Premium (Recommended)")
    st.markdown("**£24.99 / month**")
    for f in premium_features:
        st.markdown(f"- ✅ {f}")
    if st.button("Upgrade to Premium (Test)", key="upgrade_premium"):
        url = None
        if email_sidebar:
            url = create_checkout_session("price_xxxxx_premium", email_sidebar)
        if url:
            st.markdown(f"[Proceed to Checkout]({url})")
        else:
            st.info("Checkout not configured — set Stripe keys & price IDs in environment.")

st.markdown("---")
st.caption("DealerCommand • Built for dealerships • 2025")


