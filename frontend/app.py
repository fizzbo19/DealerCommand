import streamlit as st
import datetime
import json
from openai import OpenAI
import gspread
import stripe
from google.oauth2.service_account import Credentials

TRIAL_DURATION_DAYS = 30  # 30 days

# --- Google Sheets Setup ---
def get_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials_info = json.loads(st.secrets["google"]["credentials_json"])
    creds = Credentials.from_service_account_info(credentials_info, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(
        "https://docs.google.com/spreadsheets/d/12UDiRnjQXwxcHFjR3SWdz8lB45-OTGHBzm3YVcExnsQ/edit"
    ).sheet1
    return sheet


def get_user_row(sheet, user_email):
    records = sheet.get_all_records()
    for i, r in enumerate(records, start=2):
        if r["Email"] == user_email:
            return i, r
    return None, None


def save_user_usage(user_email, listing_text):
    sheet = get_sheet()
    row_idx, record = get_user_row(sheet, user_email)
    today = datetime.date.today()

    if record:
        new_count = int(record["Listings Generated"]) + 1
        sheet.update_cell(row_idx, 4, new_count)
    else:
        expiry_date = today + datetime.timedelta(days=TRIAL_DURATION_DAYS)
        sheet.append_row([user_email, str(today), str(expiry_date), 1])

    # Optional: store listing text in another tab for history
    try:
        history_sheet = sheet.spreadsheet.worksheet("Listings History")
    except gspread.exceptions.WorksheetNotFound:
        history_sheet = sheet.spreadsheet.add_worksheet(title="Listings History", rows=1000, cols=5)
        history_sheet.append_row(["Email", "Date", "Car", "Listing", "Tone"])

    history_sheet.append_row([user_email, str(today), "-", listing_text[:500], "-"])


def get_trial_status(user_email):
    sheet = get_sheet()
    _, record = get_user_row(sheet, user_email)
    if not record:
        return "new", None, 0
    expiry_date = datetime.datetime.strptime(record["Trial Ends"], "%Y-%m-%d").date()
    used = int(record["Listings Generated"])
    if datetime.date.today() > expiry_date:
        return "expired", expiry_date, used
    return "active", expiry_date, used


# --- Streamlit UI ---
st.set_page_config(page_title="🚗 DealerCommand AI", layout="centered")
st.title("🚗 DealerCommand AI – Smart Dealer Assistant")

st.markdown("### Welcome to your AI-powered dealership toolkit.")
user_email = st.text_input("Enter your email to start (for trial tracking):")

if user_email:
    status, expiry, used = get_trial_status(user_email)

    if status == "expired":
        st.error("⏰ Your free 3-month trial has ended. Please upgrade to continue using DealerCommand.")
        st.markdown("[Upgrade Here 🔗](#)")  # link placeholder for Stripe
        st.stop()
    else:
        if status == "new":
            st.info("✨ Welcome! Your 3-month free trial starts today.")
        elif status == "active":
            days_left = (expiry - datetime.date.today()).days
            st.success(f"✅ Trial Active – {days_left} days left | {used} listings generated")

        api_key = st.text_input("Enter your OpenAI API key", type="password")

        with st.form("car_form"):
            make = st.text_input("Car Make", "BMW")
            model = st.text_input("Model", "X5 M Sport")
            year = st.text_input("Year", "2021")
            mileage = st.text_input("Mileage", "28,000 miles")
            color = st.text_input("Color", "Black")
            fuel = st.selectbox("Fuel Type", ["Petrol", "Diesel", "Hybrid", "Electric"])
            transmission = st.selectbox("Transmission", ["Automatic", "Manual"])
            price = st.text_input("Price", "£45,995")
            tone = st.selectbox("Tone/Style", ["Professional", "Sporty", "Luxury", "Casual"])
            features = st.text_area("Key Features", "Panoramic roof, heated seats, M Sport package")
            notes = st.text_area("Dealer Notes (optional)", "Full service history, finance available")
            submit = st.form_submit_button("Generate Listing")

        if submit:
            if not api_key:
                st.warning("⚠️ Please enter your OpenAI API key to generate listings.")
            else:
                client = OpenAI(api_key=api_key)
                prompt = f"""
                You are an AI assistant for car dealerships.
                Write a {tone.lower()} car listing for:
                {year} {make} {model} ({color}), {mileage}, {fuel}, {transmission}.
                Price: {price}.
                Features: {features}.
                Dealer Notes: {notes}.
                Include emojis, persuasive language, and clear paragraphs.
                """

                with st.spinner("Generating your car listing..."):
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.8,
                    )
                    listing = response.choices[0].message.content

                st.subheader("📋 AI-Generated Listing:")
                st.markdown(listing)

                st.download_button("⬇️ Download Listing", listing, file_name="car_listing.txt")

                # Generate social caption
                caption_prompt = f"Create a short, catchy Instagram/TikTok caption for this car: {make} {model}. Include relevant emojis and hashtags."
                caption_response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": caption_prompt}],
                    temperature=0.9,
                )
                caption = caption_response.choices[0].message.content
                st.subheader("📱 Suggested Caption:")
                st.markdown(caption)

                save_user_usage(user_email, listing)
                st.success("✅ Listing saved and trial usage updated!")

                # Initialize Stripe
stripe.api_key = st.secrets["stripe"]["secret_key"]

def create_checkout_session(price_id, user_email):
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            customer_email=user_email,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url="https://dealercommand.onrender.com?success=true",
            cancel_url="https://dealercommand.onrender.com?canceled=true",
        )
        return checkout_session.url
    except Exception as e:
        st.error(f"Error creating checkout: {e}")
        return None


# Pricing & Upgrade Section
st.markdown("---")
st.header("💰 Upgrade Plans")

col1, col2 = st.columns(2)
with col1:
    st.subheader("🚀 Starter Plan")
    st.markdown("Perfect for small dealerships\n**£9.99/month**\n- 15 listings/month\n- Social media captions\n- Basic analytics")
    if st.button("Upgrade to Starter (£9.99)"):
        url = create_checkout_session("price_xxxxx_starter", user_email)
        if url:
            st.markdown(f"[👉 Proceed to Payment]({url})")

with col2:
    st.subheader("🏆 Pro Plan")
    st.markdown("For high-volume dealers\n**£24.99/month**\n- Unlimited listings\n- Advanced analytics\n- Priority support")
    if st.button("Upgrade to Pro (£24.99)"):
        url = create_checkout_session("price_xxxxx_pro", user_email)
        if url:
            st.markdown(f"[👉 Proceed to Payment]({url})")



                

