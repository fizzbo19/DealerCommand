# frontend/app.py
import sys, os, json
from datetime import datetime
import streamlit as st
from openai import OpenAI

# Local imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.trial_manager import ensure_user_and_get_status, increment_usage
from backend.sheet_utils import append_to_google_sheet
from backend.stripe_utils import create_checkout_session

# Optional (if you add animation later)
try:
    from streamlit_lottie import st_lottie
except ImportError:
    st_lottie = None

# ----------------------
# PAGE CONFIG
# ----------------------
st.set_page_config(
    page_title="DealerCommand AI | Smart Automotive Listings",
    layout="wide",
    page_icon="🚗"
)

# ----------------------
# ASSETS PATHS & LOGO
# ----------------------
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
LOGO_FILE = os.path.join(ASSETS_DIR, "dealercommand_logov1.png")

# ----------------------
# SIDEBAR LOGO
# ----------------------
if os.path.exists(LOGO_FILE):
    st.sidebar.image(LOGO_FILE, width=160, caption="DealerCommand AI")
else:
    st.sidebar.markdown("**DealerCommand AI**")  # fallback text

# ----------------------
# HERO LOGO
# ----------------------
if os.path.exists(LOGO_FILE):
    st.markdown(f"""
    <div style="display:flex; justify-content:center; align-items:center; margin-top:1rem; margin-bottom:1rem;">
        <img src="{LOGO_FILE}" alt="DealerCommand AI Logo" width="200" style="border-radius:12px;"/>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown('<h2 style="text-align:center;">🚗 DealerCommand AI</h2>', unsafe_allow_html=True)

# ----------------------
# HERO TITLE & SUBTITLE
# ----------------------
st.markdown('<div class="hero-title">🚗 DealerCommand AI</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-sub">Create high-converting, SEO-optimised car listings in seconds with AI.</div>', unsafe_allow_html=True)

# ----------------------
# CUSTOM CSS
# ----------------------
st.markdown("""
<style>
body {
    background-color: #f9fafb;
    color: #111827;
    font-family: 'Inter', sans-serif;
}
.main {
    padding-top: 0rem;
}
.hero-title {
    font-size: 2.4rem;
    font-weight: 700;
    text-align: center;
    color: #111827;
    margin-bottom: 0.4rem;
}
.hero-sub {
    text-align: center;
    color: #6b7280;
    font-size: 1.1rem;
    margin-bottom: 2.5rem;
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
.footer {
    text-align: center;
    color: #9ca3af;
    font-size: 0.9rem;
    margin-top: 3rem;
}
</style>
""", unsafe_allow_html=True)

# ----------------------
# MAIN LOGIC
# ----------------------
user_email = st.text_input("📧 Dealership email", placeholder="e.g. sales@autohub.co.uk")
api_key = os.environ.get("OPENAI_API_KEY")

if not api_key:
    st.error("⚠️ Missing OpenAI key — set `OPENAI_API_KEY` in Render environment.")
    st.stop()

if user_email:
    status, expiry, usage_count = ensure_user_and_get_status(user_email)
    is_active = status in ["active", "new"]

    # ----------------------
    # SIDEBAR DASHBOARD
    # ----------------------
    st.sidebar.title("⚙️ Dashboard")
    st.sidebar.markdown(f"**👤 User:** {user_email}")
    st.sidebar.markdown(f"**📅 Trial Ends:** {expiry}")
    st.sidebar.markdown(f"**📊 Listings Used:** {usage_count} / 15")
    usage_percent = min((usage_count / 15) * 100, 100)
    st.sidebar.progress(int(usage_percent))

    if is_active:
        st.sidebar.markdown('<span style="color:#10b981;">🟢 Trial Active</span>', unsafe_allow_html=True)
    else:
        st.sidebar.markdown('<span style="color:#ef4444;">🔴 Trial Expired</span>', unsafe_allow_html=True)
        if st.sidebar.button("💳 Upgrade Plan"):
            checkout_url = create_checkout_session(user_email)
            st.sidebar.markdown(f"[👉 Upgrade to Pro]({checkout_url})", unsafe_allow_html=True)

    st.sidebar.markdown("---")
    st.sidebar.markdown("💬 **Need help?** [Contact support](mailto:support@dealercommand.ai)")

    # ----------------------
    # MAIN CONTENT
    # ----------------------
    if is_active:
        st.markdown("### 🧾 Generate a New Listing")
        st.caption("Complete the details below and let AI handle the rest.")

        with st.form("listing_form"):
            col1, col2 = st.columns(2)
            with col1:
                make = st.text_input("Car Make", "BMW")
                model = st.text_input("Model", "X5 M Sport")
                year = st.text_input("Year", "2021")
                mileage = st.text_input("Mileage", "28,000 miles")
                color = st.text_input("Color", "Black")
            with col2:
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
                    if st_lottie and os.path.exists(os.path.join(ASSETS_DIR, "ai_loading.json")):
                        with open(os.path.join(ASSETS_DIR, "ai_loading.json"), "r") as f:
                            lottie_ai = json.load(f)
                        st_lottie(lottie_ai, height=120, key="ai_loading")

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
        st.warning("⚠️ Your trial has ended. Please upgrade to continue.")
        if st.button("💳 Upgrade Now"):
            checkout_url = create_checkout_session(user_email)
            st.markdown(f"[👉 Click here to upgrade your plan]({checkout_url})", unsafe_allow_html=True)

else:
    st.info("👋 Enter your dealership email above to begin your 3-month premium trial.")

# ----------------------
# FOOTER
# ----------------------
st.markdown('<div class="footer">© 2025 DealerCommand AI — Powered by Carfundo</div>', unsafe_allow_html=True)
