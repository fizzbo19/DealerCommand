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
from backend.sheet_utils import append_to_google_sheet, get_user_activity_data
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
.footer { text-align: center; color: #9ca3af; font-size: 0.9rem; margin-top: 3rem; }
.card { background: linear-gradient(135deg, #ffffff, #f0f4f8); border-radius: 16px; padding: 1.2rem; box-shadow: 0 6px 20px rgba(0,0,0,0.08); margin-bottom: 1.5rem; transition: transform 0.3s ease, box-shadow 0.3s ease; position: relative; }
.card:hover { transform: translateY(-5px); box-shadow: 0 12px 30px rgba(0,0,0,0.12); }
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

    expiry_date = datetime.strptime(expiry, "%Y-%m-%d") if isinstance(expiry, str) else expiry
    remaining_days = (expiry_date - datetime.now()).days

    # Sidebar Tabs
    sidebar_tabs = st.sidebar.tabs(["🎯 Trial Overview", "💳 Upgrade Plans", "⚙️ User Settings"])

    # ----------------------
    # TRIAL OVERVIEW TAB
    # ----------------------
    with sidebar_tabs[0]:
        st.markdown("### 🎯 Your DealerCommand Trial")
        st.markdown(f"**👤 Email:** `{user_email}`")
        st.markdown(f"**📊 Listings Used:** `{usage_count}` / 15")
        st.progress(int(min((usage_count / 15) * 100, 100)))

        if is_active and remaining_days > 0:
            st.markdown(f"**🟢 Status:** Active Trial")
            st.markdown(f"**⏳ Days Remaining:** `{remaining_days}` days")
            st.markdown(f"**📅 Ends On:** `{expiry_date.strftime('%B %d, %Y')}`")
        else:
            st.error("🚫 Your trial has expired. Upgrade to continue using DealerCommand.")

    # ----------------------
    # UPGRADE PLANS TAB
    # ----------------------
    with sidebar_tabs[1]:
        st.markdown("### 💳 Upgrade Your Plan")
        st.caption("Select a plan to unlock more listings, analytics, and support.")

        # --- Starter Plan ---
        st.markdown("#### 🚀 Starter Plan – £29/month")
        st.markdown("""
        **Perfect for independent dealers and small teams.**  
        - Up to 50 listings/month  
        - Basic analytics dashboard  
        - Email support  
        """)
        if st.button("Upgrade to Starter (£29/mo)", key="starter_plan_btn"):
            checkout_url = create_checkout_session(user_email, plan="starter")
            st.success("Redirecting to payment page...")
            st.markdown(f"[Proceed to Checkout]({checkout_url})", unsafe_allow_html=True)
            time.sleep(1)

        st.markdown("---")

        # --- Pro Plan ---
        st.markdown("#### 💼 Pro Plan – £59/month")
        st.markdown("""
        **Ideal for growing dealerships and marketing professionals.**  
        - Unlimited listings  
        - Advanced analytics  
        - Team access  
        - Priority support  
        """)
        if st.button("Upgrade to Pro (£59/mo)", key="pro_plan_btn"):
            checkout_url = create_checkout_session(user_email, plan="pro")
            st.success("Redirecting to payment page...")
            st.markdown(f"[Proceed to Checkout]({checkout_url})", unsafe_allow_html=True)
            time.sleep(1)

        st.markdown("---")
        st.info("Need help choosing a plan? [Book a free consultation](https://www.carfundo.com/contact) 📞")

        # --- Keep your existing Premium & Pro Expander Plans ---
        with st.expander("🚗 Premium – £29.99/month"):
            st.markdown("""
            **Perfect for independent dealers & small teams.**  
            - Unlimited car listings with full AI assistant  
            - Advanced analytics dashboard  
            - Team management features  
            - Priority email support  
            - Export to AutoTrader, Facebook & eBay  
            - Weekly dealership insights reports  
            """)
            if user_email:
                checkout_url = create_checkout_session(user_email, plan="premium")
                st.markdown(f"[🔗 Upgrade to Premium]({checkout_url})", unsafe_allow_html=True)

        with st.expander("⚡ Pro – £59.99/month"):
            st.markdown("""
            **Best for multi-location dealerships & power users.**  
            - Everything in Premium  
            - Advanced AI SEO optimisation tools  
            - Cross-platform marketing insights  
            - Priority email + live chat support  
            - Custom reporting & performance dashboards  
            - Social media content generation suite  
            - Dedicated account manager  
            """)
            if user_email:
                checkout_url = create_checkout_session(user_email, plan="pro")
                st.markdown(f"[🚀 Upgrade to Pro]({checkout_url})", unsafe_allow_html=True)

        st.markdown("---")
        st.info("Need help choosing? Email us at [info@dealercommand.tech](mailto:info@dealercommand.tech)")

    # ----------------------
    # USER SETTINGS TAB
    # ----------------------
    with sidebar_tabs[2]:
        st.markdown("### ⚙️ Account Settings")
        st.caption("View and manage your current plan and activity.")
        st.markdown(f"**Current Status:** `{status}`")
        st.markdown(f"**Trial Expiry:** `{expiry_date.strftime('%Y-%m-%d')}`")
        st.markdown(f"**Total Listings Used:** `{usage_count}`")

    # ----------------------
    # MAIN CONTENT TABS
    # ----------------------
    main_tabs = st.tabs(["🧾 Generate Listing", "📊 Analytics Dashboard", "📈 User Activity"])

    # --- Generate Listing ---
    with main_tabs[0]:
        if is_active and remaining_days > 0:
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
Write a 120–150 word engaging car listing:
{year} {make} {model}, {mileage}, {color}, {fuel}, {transmission}, {price}.
Features: {features}. Dealer Notes: {notes}.
Include emojis and SEO-rich phrasing.
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
                        "Response Time (s)": round(duration, 2),
                        "Make": make,
                        "Model Name": model,
                        "Year": year
                    }
                    append_to_google_sheet("AI_Metrics", ai_metrics)
                    increment_usage(user_email, 1)
                except Exception as e:
                    st.error(f"⚠️ Error: {e}")
        else:
            st.warning("⚠️ Your trial has ended. Please upgrade to continue.")

    # --- Analytics Dashboard ---
    with main_tabs[1]:
        st.markdown("### 📊 Social Media Analytics (Premium)")
        st.info("Upgrade to view engagement analytics, conversion rates, and SEO performance.")

    # --- User Activity ---
    with main_tabs[2]:
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
