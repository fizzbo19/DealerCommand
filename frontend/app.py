# frontend/app.py
import sys, os
from datetime import datetime
import streamlit as st
from openai import OpenAI

# Add backend path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.trial_manager import ensure_user_and_get_status, increment_usage
from backend.sheet_utils import append_to_google_sheet
from backend.stripe_utils import create_checkout_session

# ----------------------
# Page Setup
# ----------------------

st.image("frontend/assets/dealercommand_logo.png", width=180)

st.set_page_config(
    page_title="DealerCommand AI | Smart Automotive Listings",
    layout="wide",
    page_icon="🚗"
)

# Inject Custom CSS
st.markdown("""
<style>
/* General body styling */
body {
    background-color: #f9fafb;
    color: #111827;
    font-family: 'Inter', sans-serif;
}

/* Main container */
.main {
    padding-top: 1rem;
    padding-bottom: 2rem;
}

/* Hero section */
.hero-title {
    font-size: 2.6rem;
    font-weight: 700;
    text-align: center;
    color: #111827;
    margin-bottom: 0.5rem;
}
.hero-sub {
    text-align: center;
    color: #6b7280;
    font-size: 1.1rem;
    margin-bottom: 2.5rem;
}

/* Input boxes and buttons */
.stTextInput > div > div > input {
    border-radius: 10px;
    border: 1px solid #e5e7eb;
    padding: 10px;
}
.stButton > button {
    background: linear-gradient(90deg, #2563eb, #1e40af);
    color: white;
    border-radius: 10px;
    padding: 0.6rem 1.4rem;
    font-weight: 600;
    border: none;
    transition: 0.2s ease-in-out;
}
.stButton > button:hover {
    background: linear-gradient(90deg, #1e40af, #2563eb);
    transform: scale(1.02);
}
.stDownloadButton > button {
    background: #10b981;
    color: white;
    border-radius: 8px;
    font-weight: 500;
}

/* Cards */
.block-container {
    max-width: 900px;
    margin: auto;
}

/* Success / Warning Styling */
.stSuccess {
    background-color: #ecfdf5;
    border-left: 4px solid #10b981;
    color: #065f46;
}
.stWarning {
    background-color: #fff7ed;
    border-left: 4px solid #f59e0b;
    color: #78350f;
}

/* Footer */
.footer {
    text-align: center;
    color: #9ca3af;
    font-size: 0.9rem;
    margin-top: 3rem;
}
</style>
""", unsafe_allow_html=True)

# ----------------------
# Hero Section
# ----------------------
st.markdown('<div class="hero-title">🚗 DealerCommand AI</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-sub">Create high-converting, SEO-optimised car listings in seconds with AI.</div>', unsafe_allow_html=True)

# ----------------------
# Main Logic
# ----------------------
user_email = st.text_input("📧 Dealership email", placeholder="e.g. sales@autohub.co.uk")
api_key = os.environ.get("OPENAI_API_KEY")

if not api_key:
    st.error("⚠️ Missing OpenAI key — set `OPENAI_API_KEY` in Render environment.")
    st.stop()

if user_email:
    status, expiry, usage_count = ensure_user_and_get_status(user_email)
    is_active = status in ["active", "new"]

    if is_active:
        st.success(f"🎉 Trial Active — Ends: **{expiry}** | Listings Used: **{usage_count}**")
    else:
        st.warning("⚠️ Trial expired. Upgrade to continue.")
        if st.button("💳 Upgrade Now"):
            try:
                checkout_url = create_checkout_session(user_email)
                st.markdown(f"[👉 Upgrade to Pro]({checkout_url})", unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Payment error: {e}")

    if is_active:
        with st.form("listing_form"):
            st.subheader("🧾 Generate New Car Listing")
            make = st.text_input("Car Make", "BMW")
            model = st.text_input("Model", "X5 M Sport")
            year = st.text_input("Year", "2021")
            mileage = st.text_input("Mileage", "28,000 miles")
            color = st.text_input("Color", "Black")
            fuel = st.selectbox("Fuel Type", ["Petrol", "Diesel", "Hybrid", "Electric"])
            transmission = st.selectbox("Transmission", ["Automatic", "Manual"])
            price = st.text_input("Price", "£45,995")
            features = st.text_area("Key Features", "Panoramic roof, heated seats, M Sport package")
            notes = st.text_area("Dealer Notes (optional)", "Full service history, finance available")
            submitted = st.form_submit_button("✨ Generate Listing")

        if submitted:
            try:
                client = OpenAI(api_key=api_key)
                prompt = f"""
You are an expert automotive marketing assistant.
Write a professional, engaging listing for this car:

Make: {make}
Model: {model}
Year: {year}
Mileage: {mileage}
Color: {color}
Fuel: {fuel}
Transmission: {transmission}
Price: {price}
Features: {features}
Dealer Notes: {notes}

Guidelines:
- 100–150 words
- Emphasise the car’s best features
- Add relevant emojis
- Optimised for online car marketplaces
"""
                with st.spinner("🤖 Generating your listing..."):
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "You are a top-tier automotive copywriter."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.7,
                    )
                    listing = response.choices[0].message.content.strip()

                st.success("✅ Listing generated successfully!")
                st.markdown(f"### 📋 Your AI-Optimised Listing\n\n{listing}")
                st.download_button("⬇ Download Listing", listing, file_name="listing.txt")

                car_data = {
                    "Make": make, "Model": model, "Year": year, "Mileage": mileage,
                    "Color": color, "Fuel Type": fuel, "Transmission": transmission,
                    "Price": price, "Features": features, "Dealer Notes": notes
                }
                append_to_google_sheet(user_email, car_data)
                increment_usage(user_email, listing)

            except Exception as e:
                st.error(f"⚠️ Error: {e}")
else:
    st.info("👋 Enter your email to begin your 3-month premium trial.")

# ----------------------
# Footer
# ----------------------
st.markdown('<div class="footer">© 2025 DealerCommand AI — Powered by Carfundo</div>', unsafe_allow_html=True)
