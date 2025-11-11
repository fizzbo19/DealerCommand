# frontend/app.py
import sys, os, json, time
from datetime import datetime
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
    st.markdown(f"""
    <div style="display:flex; justify-content:center; align-items:center; margin-top:1rem; margin-bottom:1rem;">
        <img src="{LOGO_FILE}" alt="DealerCommand AI Logo" width="200" style="border-radius:12px;">
    </div>
    """, unsafe_allow_html=True)
else:
    st.sidebar.markdown("**DealerCommand AI**")
    st.markdown('<h2 style="text-align:center;">🚗 DealerCommand AI</h2>', unsafe_allow_html=True)

st.markdown('<div class="hero-sub">Create high-converting, SEO-optimised car listings in seconds with AI.</div>', unsafe_allow_html=True)

# ----------------------
# CUSTOM CSS
# ----------------------
st.markdown("""
<style>
body { background-color: #f9fafb; color: #111827; font-family: 'Inter', sans-serif; }
.stButton > button { background: linear-gradient(90deg, #2563eb, #1e40af); color: white; border-radius: 10px; padding: 0.6rem 1.4rem; font-weight: 600; border: none; transition: 0.2s ease-in-out; }
.stButton > button:hover { background: linear-gradient(90deg, #1e40af, #2563eb); transform: scale(1.02); }
.stDownloadButton > button { background: #10b981; color: white; border-radius: 8px; font-weight: 500; }
.footer { text-align: center; color: #9ca3af; font-size: 0.9rem; margin-top: 3rem; }
.card { background: linear-gradient(135deg, #ffffff, #f0f4f8); border-radius: 16px; padding: 1.2rem; box-shadow: 0 6px 20px rgba(0,0,0,0.08); margin-bottom: 1.5rem; transition: transform 0.3s ease, box-shadow 0.3s ease; position: relative; }
.card:hover { transform: translateY(-5px); box-shadow: 0 12px 30px rgba(0,0,0,0.12); }
.card img { border-radius: 12px; }
.ribbon { position: absolute; top: -10px; right: -10px; background: #10b981; color: white; padding: 0.4rem 1rem; font-weight: 600; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.2); }
.feature-icon { display: inline-block; background: #2563eb; color: white; border-radius: 50%; width: 22px; height: 22px; text-align: center; line-height: 22px; margin-right: 6px; font-size: 14px; }
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

# ==========================================================
# 🎯 DEALERCOMMAND SUBSCRIPTION LOGIC
# ==========================================================
if user_email:
    status, expiry, usage_count = ensure_user_and_get_status(user_email)
    is_active = status in ["active", "new"]

    # Convert expiry to datetime and compute remaining days
    # expiry is already a datetime object
    expiry_date = expiry
    remaining_days = (expiry_date - datetime.now()).days


    # ----------------------
    # SIDEBAR DASHBOARD
    # ----------------------
    st.sidebar.title("⚙️ Dashboard")
    st.sidebar.markdown(f"**👤 User:** {user_email}")
    st.sidebar.markdown(f"**📊 Listings Used:** {usage_count} / 15")
    st.sidebar.progress(int(min((usage_count / 15) * 100, 100)))

if is_active and remaining_days > 0:
    st.sidebar.markdown(f"<span style='color:#10b981;'>🟢 Trial Active</span>", unsafe_allow_html=True)
    st.sidebar.markdown(f"**⏳ Days Remaining:** {remaining_days} days")
    st.sidebar.markdown(f"**📅 Trial Ends:** {expiry_date.strftime('%B %d, %Y')}")
else:
    st.sidebar.markdown(f"<span style='color:#ef4444;'>🔴 Trial Expired</span>", unsafe_allow_html=True)
    st.sidebar.warning("Your trial has ended. Upgrade below to continue using DealerCommand.")


    # ----------------------
    # SIDEBAR UPGRADE PLANS
    # ----------------------
    st.sidebar.markdown("### 💳 Choose Your Plan")
    calendly_link = "https://calendly.com/fizmaygroup-info/30min"

    def sidebar_upgrade_button(plan_name, plan_label, plan_price):
        checkout_url = create_checkout_session(user_email, plan=plan_name)
        st.sidebar.markdown(f"""
        <div class="plan-card">
            <div class="plan-title">{plan_label}</div>
            <div class="plan-price">£{plan_price} / mo</div>
            <a href="{checkout_url}" target="_blank" class="plan-btn btn-premium">Upgrade</a>
        </div>
        """, unsafe_allow_html=True)

    st.sidebar.markdown(f"""
    <a href="{calendly_link}" target="_blank" class="plan-btn btn-consult">📅 Book Free 30-min Consultation</a>
    """, unsafe_allow_html=True)
    st.sidebar.markdown("---")
    st.sidebar.markdown("💬 **Need help?** [Contact support](mailto:info@dealercommand.tech)")

    # ----------------------
    # TABS: Listings | Analytics | Activity
    # ----------------------
    tabs = st.tabs(["🧾 Generate Listing", "📊 Analytics Dashboard", "📈 User Activity"])

    # ----------------------
    # TAB 1: LISTING GENERATOR
    # ----------------------
    with tabs[0]:
        if is_active and remaining_days > 0:
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
                    car_image = st.file_uploader("Upload Car Image (optional)", type=["png","jpg","jpeg"])
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
                    seo_prompt = f"Generate 3 SEO-friendly titles for a {year} {make} {model} {color}."
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

                    prompt = f"""
Write a 100–150 word engaging car listing:
{year} {make} {model}, {mileage}, {color}, {fuel}, {transmission}, {price}.
Features: {features}. Dealer Notes: {notes}.
Include emojis and SEO flair.
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

                    st.success("✅ Listing generated successfully!")
                    duration = time.time() - start_time

                    st.markdown(f"**Generated Listing:**\n\n{listing_text}")
                    st.download_button("⬇ Download Listing", listing_text, file_name="listing.txt")

                    ai_metrics = {
                        "Email": user_email,
                        "Timestamp": datetime.now().isoformat(),
                        "Model": "gpt-4o-mini",
                        "Response Time (s)": round(duration,2),
                        "Make": make,
                        "Model Name": model,
                        "Year": year
                    }
                    append_to_google_sheet("AI_Metrics", ai_metrics)
                    increment_usage(user_email, listing_text)

                except Exception as e:
                    st.error(f"⚠️ Error: {e}")
        else:
            st.warning("⚠️ Your trial has ended. Please upgrade to continue.")

    # ----------------------
    # TAB 2: ANALYTICS DASHBOARD (placeholder)
    # ----------------------
    with tabs[1]:
        st.markdown("### 📊 Social Media Analytics (Premium)")
        st.info("Upgrade to view performance insights and engagement analytics.")

    # ----------------------
    # TAB 3: USER ACTIVITY
    # ----------------------
    with tabs[2]:
        st.markdown("### 📈 User Activity Overview")
        try:
            activity_data = get_user_activity_data(user_email)
            st.dataframe(activity_data)
        except Exception as e:
            st.error(f"⚠️ Could not load user activity: {e}")

else:
    st.info("👋 Enter your dealership email above to begin your 30-day Pro trial.")

# ----------------------
# FOOTER
# ----------------------
st.markdown(
    '<div class="footer">© 2025 DealerCommand AI — Powered by FizMay Group</div>', 
    unsafe_allow_html=True
)
