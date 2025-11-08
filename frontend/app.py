# frontend/app.py
import sys, os, json, time
from datetime import datetime, date
import streamlit as st
from openai import OpenAI
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Local imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.trial_manager import ensure_user_and_get_status, increment_usage
from backend.sheet_utils import append_to_google_sheet, get_user_activity_data, get_social_media_data
from backend.stripe_utils import create_checkout_session

# ----------------------
# PAGE CONFIG
# ----------------------
st.set_page_config(
    page_title="DealerCommand AI | Smart Automotive Listings",
    layout="wide",
    page_icon="🚗"
)

# ----------------------
# BRANDING & LOGO
# ----------------------
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
LOGO_FILE = os.path.join(ASSETS_DIR, "dealercommand_logov1.png")

if os.path.exists(LOGO_FILE):
    st.sidebar.image(LOGO_FILE, width=160, caption="DealerCommand AI")
else:
    st.sidebar.markdown("**DealerCommand AI**")

if os.path.exists(LOGO_FILE):
    st.markdown(f"""
    <div style="display:flex; justify-content:center; align-items:center; margin-top:1rem; margin-bottom:1rem;">
        <img src="{LOGO_FILE}" alt="DealerCommand AI Logo" width="200" style="border-radius:12px;">
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown('<h2 style="text-align:center;">🚗 DealerCommand AI</h2>', unsafe_allow_html=True)

st.markdown('<div class="hero-sub">Create high-converting, SEO-optimised car listings in seconds with AI.</div>', unsafe_allow_html=True)

# ----------------------
# CUSTOM CSS
# ----------------------
st.markdown("""
<style>
body { background-color: #f9fafb; color: #111827; font-family: 'Inter', sans-serif; }
.main { padding-top: 0rem; }
.hero-title { font-size: 2.4rem; font-weight: 700; text-align: center; color: #111827; margin-bottom: 0.4rem; }
.hero-sub { text-align: center; color: #6b7280; font-size: 1.1rem; margin-bottom: 2.5rem; }
.stButton > button { background: linear-gradient(90deg, #2563eb, #1e40af); color: white; border-radius: 10px; padding: 0.6rem 1.4rem; font-weight: 600; border: none; transition: 0.2s ease-in-out; }
.stButton > button:hover { background: linear-gradient(90deg, #1e40af, #2563eb); transform: scale(1.02); }
.stDownloadButton > button { background: #10b981; color: white; border-radius: 8px; font-weight: 500; }
.footer { text-align: center; color: #9ca3af; font-size: 0.9rem; margin-top: 3rem; }
[data-testid="stMetricValue"] { color: #1d4ed8 !important; font-weight: 700 !important; }
[data-testid="stMetricLabel"] { color: #6b7280 !important; }

.card {
    background: linear-gradient(135deg, #ffffff, #f0f4f8);
    border-radius: 16px;
    padding: 1.2rem;
    box-shadow: 0 6px 20px rgba(0,0,0,0.08);
    margin-bottom: 1.5rem;
    transition: transform 0.3s ease, box-shadow 0.3s ease;
    position: relative;
}
.card:hover {
    transform: translateY(-5px);
    box-shadow: 0 12px 30px rgba(0,0,0,0.12);
}
.card img {
    border-radius: 12px;
}
.ribbon {
    position: absolute;
    top: -10px;
    right: -10px;
    background: #10b981;
    color: white;
    padding: 0.4rem 1rem;
    font-weight: 600;
    border-radius: 8px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.2);
}
.feature-icon {
    display: inline-block;
    background: #2563eb;
    color: white;
    border-radius: 50%;
    width: 22px;
    height: 22px;
    text-align: center;
    line-height: 22px;
    margin-right: 6px;
    font-size: 14px;
}
</style>
""", unsafe_allow_html=True)

# ----------------------
# MAIN APP LOGIC
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
    st.sidebar.progress(int(min((usage_count / 15) * 100, 100)))

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
    # TABS: Listings | Analytics | Leaderboard
    # ----------------------
    tabs = st.tabs(["🧾 Generate Listing", "📊 Analytics Dashboard", "🏆 Dealer Leaderboard"])

    # ----------------------
    # LISTING GENERATOR (Premium Marketplace UI)
    # ----------------------
    with tabs[0]:
        if is_active:
            st.markdown("### 🧾 Generate a New Listing")
            st.caption("Complete the details below and let AI handle the rest. Upload images to make your listing stand out!")

            with st.form("listing_form"):
                col1, col2 = st.columns(2)
                with col1:
                    make = st.text_input("Car Make", "BMW")
                    model = st.text_input("Model", "X5 M Sport")
                    year = st.text_input("Year", "2021")
                    mileage = st.text_input("Mileage", "28,000 miles")
                    color = st.text_input("Color", "Black")
                    car_image = st.file_uploader("Upload Car Image (optional)", type=["png","jpg","jpeg"], key="car_image")
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

                    # SEO Titles
                    seo_prompt = f"Generate 3 SEO-friendly car listing titles for a {year} {make} {model} {color}, emphasizing features: {features}."
                    seo_response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role":"system","content":"You are a marketing copywriter specialized in automotive listings."},
                            {"role":"user","content":seo_prompt}
                        ],
                        temperature=0.7
                    )
                    seo_titles = seo_response.choices[0].message.content.strip()
                    st.info(f"💡 Suggested SEO Titles:\n{seo_titles}")

                    # Full Listing
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
- Include emojis and highlights
- Optimised for online car marketplaces and SEO
"""
                    start_time = time.time()
                    with st.spinner("🤖 Generating your listing..."):
                        response = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {"role":"system","content":"You are a top-tier automotive copywriter."},
                                {"role":"user","content":prompt}
                            ],
                            temperature=0.7
                        )
                        listing_text = response.choices[0].message.content.strip()
                    duration = time.time() - start_time

                    st.success("✅ Listing generated successfully!")

                    # Premium Marketplace Card UI with ribbon & feature icons
                    st.markdown('<div class="card">', unsafe_allow_html=True)
                    st.markdown(f'<div class="ribbon">{price}</div>', unsafe_allow_html=True)
                    card_cols = st.columns([1,2])
                    with card_cols[0]:
                        if car_image:
                            st.image(car_image, use_column_width=True)
                        else:
                            st.image("https://via.placeholder.com/300x200.png?text=Car+Image", use_column_width=True)
                    with card_cols[1]:
                        st.markdown(f"### {year} {make} {model}")
                        st.markdown(f"**Mileage:** {mileage}")
                        st.markdown(f"**Color:** {color}")
                        st.markdown(f"**Fuel:** {fuel} | **Transmission:** {transmission}")
                        st.markdown("**Key Features:**")
                        for feat in features.split(","):
                            st.markdown(f'<span class="feature-icon">✓</span>{feat.strip()}', unsafe_allow_html=True)
                        if notes:
                            st.markdown(f"**Dealer Notes:** {notes}")
                        st.markdown("**Listing Description:**")
                        st.markdown(listing_text)
                    st.markdown('</div>', unsafe_allow_html=True)

                    st.download_button("⬇ Download Listing", listing_text, file_name="listing.txt")

                    # Save metrics
                    ai_metrics = {
                        "Email": user_email,
                        "Timestamp": datetime.now().isoformat(),
                        "Model": "gpt-4o-mini",
                        "Response Time (s)": round(duration,2),
                        "Prompt Length": len(prompt),
                        "Make": make,
                        "Model Name": model,
                        "Year": year,
                        "Mileage": mileage,
                        "Color": color,
                        "Fuel Type": fuel,
                        "Transmission": transmission,
                        "Price": price,
                        "Features": features,
                        "Dealer Notes": notes
                    }
                    append_to_google_sheet("AI_Metrics", ai_metrics)
                    increment_usage(user_email, listing_text)

                except Exception as e:
                    st.error(f"⚠️ Error: {e}")

        else:
            st.warning("⚠️ Your trial has ended. Please upgrade to continue.")
            if st.button("💳 Upgrade Now"):
                checkout_url = create_checkout_session(user_email)
                st.markdown(f"[👉 Click here to upgrade your plan]({checkout_url})", unsafe_allow_html=True)

    # ----------------------
    # SOCIAL MEDIA ANALYTICS
    # ----------------------
    with tabs[1]:
        st.markdown("### 📊 Social Media Analytics (Premium)")
        # ... existing analytics code remains unchanged

    # ----------------------
    # DEALER LEADERBOARD
    # ----------------------
    with tabs[2]:
        st.markdown("### 🏆 Dealer Leaderboard")
        # ... existing leaderboard code remains unchanged

else:
    st.info("👋 Enter your dealership email above to begin your 3-month premium trial.")

# ----------------------
# FOOTER
# ----------------------
st.markdown('<div class="footer">© 2025 DealerCommand AI — Powered by Carfundo</div>', unsafe_allow_html=True)
