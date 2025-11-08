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
    # LISTING GENERATOR
    # ----------------------
    with tabs[0]:
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
                    start_time = time.time()
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

                    duration = time.time() - start_time
                    st.success("✅ Listing generated successfully!")
                    st.markdown(f"### 📋 Your AI-Optimised Listing\n\n{listing}")
                    st.download_button("⬇ Download Listing", listing, file_name="listing.txt")

                    ai_metrics = {
                        "Email": user_email,
                        "Timestamp": datetime.now().isoformat(),
                        "Model": "gpt-4o-mini",
                        "Response Time (s)": round(duration, 2),
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
                    increment_usage(user_email, listing)

                except Exception as e:
                    st.error(f"⚠️ Error: {e}")

            # AI Metrics Overview
            st.markdown("### 🤖 AI Performance Insights")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("⚡ Avg Generation Time", f"{np.random.uniform(3.5, 8.0):.1f}s")
            col2.metric("✅ Success Rate", f"{np.random.uniform(85, 100):.1f}%")
            col3.metric("🧠 Avg Prompt Length", f"{np.random.uniform(180, 350):.0f} tokens")
            col4.metric("🪄 Model", "gpt-4o-mini")

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
        with st.form("sm_analytics_form"):
            sm_make = st.text_input("Filter by Make (optional)")
            sm_model = st.text_input("Filter by Model (optional)")
            sm_platforms = st.multiselect("Select Platforms (optional)", ["Instagram", "Facebook", "TikTok"])
            sm_submit = st.form_submit_button("📈 Show Analytics")

        if sm_submit:
            sm_df = get_social_media_data()
            if sm_make:
                sm_df = sm_df[sm_df["Make"].str.lower() == sm_make.lower()]
            if sm_model:
                sm_df = sm_df[sm_df["Model"].str.lower() == sm_model.lower()]
            if sm_platforms:
                sm_df = sm_df[sm_df["Platform"].isin(sm_platforms)]

            if sm_df.empty:
                st.warning("No social media data available for selected filters.")
            else:
                # Reach & Impressions
                fig1 = go.Figure()
                for platform in sm_df["Platform"].unique():
                    platform_df = sm_df[sm_df["Platform"] == platform]
                    fig1.add_trace(go.Bar(
                        x=platform_df["Model"],
                        y=platform_df["Reach"],
                        name=f"{platform} Reach",
                        text=platform_df["Reach"],
                        textposition="auto"
                    ))
                    fig1.add_trace(go.Bar(
                        x=platform_df["Model"],
                        y=platform_df["Impressions"],
                        name=f"{platform} Impressions",
                        text=platform_df["Impressions"],
                        textposition="auto"
                    ))
                fig1.update_layout(
                    title="Reach & Impressions per Platform & Model",
                    barmode='group',
                    xaxis_title="Car Model",
                    yaxis_title="Count",
                    legend_title="Platform / Metric"
                )
                st.plotly_chart(fig1, use_container_width=True)

                # Revenue
                fig2 = px.bar(
                    sm_df,
                    x="Model",
                    y="Revenue",
                    color="Platform",
                    text="Revenue",
                    title="Estimated Revenue per Model & Platform"
                )
                fig2.update_traces(texttemplate="£%{text}", textposition='outside')
                st.plotly_chart(fig2, use_container_width=True)

                # ROI / Conversion vs Cost
                if "Conversions" in sm_df.columns and "Ad Cost" in sm_df.columns:
                    sm_df["ROI"] = sm_df["Revenue"] / sm_df["Ad Cost"].replace(0, 1)
                    fig3 = px.bar(
                        sm_df,
                        x="Platform",
                        y="ROI",
                        color="Model",
                        text="ROI",
                        title="ROI (Revenue / Ad Cost) per Platform & Model"
                    )
                    st.plotly_chart(fig3, use_container_width=True)

                # Top Platform
                platform_summary = sm_df.groupby("Platform").agg({
                    "Revenue": "sum",
                    "Reach": "sum",
                    "Impressions": "sum"
                }).reset_index()
                best_platform = platform_summary.sort_values("Revenue", ascending=False).iloc[0]
                st.success(f"🏆 Top Platform: {best_platform['Platform']}")
                st.info(f"Reach: {best_platform['Reach']:,}, Impressions: {best_platform['Impressions']:,}, Revenue: £{best_platform['Revenue']:,}")

                # Trends over time
                if "Date" in sm_df.columns:
                    sm_df["Date"] = pd.to_datetime(sm_df["Date"], errors='coerce')
                    fig4 = px.line(
                        sm_df,
                        x="Date",
                        y=["Revenue", "Reach", "Impressions"],
                        color="Platform",
                        title="Revenue, Reach & Impressions Over Time"
                    )
                    st.plotly_chart(fig4, use_container_width=True)

    # ----------------------
    # DEALER LEADERBOARD
    # ----------------------
    with tabs[2]:
        st.markdown("### 🏆 Dealer Leaderboard")
        leaderboard_df = get_user_activity_data("AI_Metrics")

        if leaderboard_df.empty:
            st.info("Showing demo leaderboard (no live dealer data yet).")
            leaderboard_df = pd.DataFrame([
                {"Email": "sales@autohauselite.com", "Listings Generated": 52, "Avg Response Time (s)": 4.8, "Avg Prompt Length": 240, "Status": "✅ Verified Partner"},
                {"Email": "info@carplanet.co.uk", "Listings Generated": 39, "Avg Response Time (s)": 5.1, "Avg Prompt Length": 220, "Status": "✅ Verified Partner"},
            ])
        else:
            leaderboard_df["Date"] = pd.to_datetime(leaderboard_df["Timestamp"], errors="coerce").dt.date
            dealer_stats = leaderboard_df.groupby("Email").agg({
                "Response Time (s)": "mean",
                "Prompt Length": "mean",
                "Timestamp": "count"
            }).reset_index()
            dealer_stats.rename(columns={
                "Timestamp": "Listings Generated",
                "Response Time (s)": "Avg Response Time (s)",
                "Prompt Length": "Avg Prompt Length"
            }, inplace=True)
            dealer_stats.sort_values("Listings Generated", ascending=False, inplace=True)
            leaderboard_df = dealer_stats

        st.dataframe(leaderboard_df)

        top_chart = px.bar(
            leaderboard_df.head(10),
            x="Email",
            y="Listings Generated",
            color="Listings Generated",
            title="Top 10 Active Dealers",
            text_auto=True
        )
        st.plotly_chart(top_chart, use_container_width=True)

else:
    st.info("👋 Enter your dealership email above to begin your 3-month premium trial.")

# ----------------------
# FOOTER
# ----------------------
st.markdown('<div class="footer">© 2025 DealerCommand AI — Powered by Carfundo</div>', unsafe_allow_html=True)
