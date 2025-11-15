# frontend/pages/3_Analytics.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, timedelta

from backend.analytics import get_user_analytics_data, platinum_recommendations

st.set_page_config(page_title="Analytics Dashboard", layout="wide")
st.title("📊 DealerCommand Analytics Dashboard")

if use_demo and not analytics_df.empty:
    show_demo_badge()


# ----------------------
# Demo Mode Badge
# ----------------------
def show_demo_badge():
    st.markdown(
        """
        <div style="
            background-color: #FFF3CD;
            border-left: 6px solid #FFCA2C;
            padding: 12px 20px;
            border-radius: 6px;
            margin-top: -10px;
            margin-bottom: 15px;
        ">
            <strong>🧪 Demo Mode:</strong> You are currently viewing demo analytics.  
            Your real data will appear automatically once you upload/create listings.
        </div>
        """,
        unsafe_allow_html=True
    )


# ----------------------
# User Info
# ----------------------
user_email = st.session_state.get("user_email")
user_plan = st.session_state.get("plan", "Pro")

if not user_email:
    st.warning("Please log in to view analytics.")
    st.stop()

# ----------------------
# Fetch Analytics Data
# ----------------------
analytics_df = get_user_analytics_data(user_email)

# ----------------------
# Demo / Live Data Toggle (Platinum only)
# ----------------------
demo_mode = False
use_demo = False
if user_plan.lower() == "platinum":
    use_demo = st.checkbox("🧪 Show Demo Analytics", value=False)

# ----------------------
# Demo Data for first-time users or demo toggle
# ----------------------
if analytics_df.empty or use_demo:
    demo_mode = True
    show_demo_badge()  # <-- BADGE ADDED HERE
    np.random.seed(42)
    demo_dates = pd.date_range(end=datetime.today(), periods=12, freq="M")
    analytics_df = pd.DataFrame({
        "Date": demo_dates,
        "Revenue": np.random.randint(2000, 10000, size=12),
        "Reach": np.random.randint(5000, 20000, size=12),
        "Impressions": np.random.randint(10000, 40000, size=12),
        "Make": np.random.choice(["BMW", "Audi", "Mercedes", "Toyota"], size=12),
        "Model": np.random.choice(["X5","A3","C-Class","Corolla"], size=12),
        "Platform": np.random.choice(["Facebook","Instagram","TikTok"], size=12),
        "Price": np.random.randint(20000, 50000, size=12)
    })
else:
    # If real data exists, do NOT show demo badge
    demo_mode = False

# ----------------------
# Filters
# ----------------------
with st.expander("🔍 Filters"):
    makes = ["All"] + analytics_df["Make"].unique().tolist()
    selected_make = st.selectbox("Select Make", makes)
    models = ["All"] + analytics_df["Model"].unique().tolist()
    selected_model = st.selectbox("Select Model", models)
    fuels = ["All"] + analytics_df.get("Fuel", pd.Series()).unique().tolist()
    selected_fuel = st.selectbox("Select Fuel Type", fuels)

filtered_df = analytics_df.copy()
if selected_make != "All":
    filtered_df = filtered_df[filtered_df["Make"] == selected_make]
if selected_model != "All":
    filtered_df = filtered_df[filtered_df["Model"] == selected_model]
if selected_fuel != "All":
    filtered_df = filtered_df[filtered_df["Fuel"] == selected_fuel]

# ----------------------
# INTERACTIVE SIMULATION (demo only)
# ----------------------
if demo_mode:
    st.subheader("🎛️ Demo Controls")
    revenue_multiplier = st.slider("Simulate Revenue Multiplier", 0.5, 2.0, 1.0, 0.1)
    listings_multiplier = st.slider("Simulate Number of Listings", 0.5, 2.0, 1.0, 0.1)

    # Apply multipliers to demo data
    filtered_df["Revenue"] = (filtered_df["Revenue"] * revenue_multiplier).astype(int)
    filtered_df["Reach"] = (filtered_df["Reach"] * listings_multiplier).astype(int)
    filtered_df["Impressions"] = (filtered_df["Impressions"] * listings_multiplier).astype(int)

# ----------------------
# PRO Charts
# ----------------------
if user_plan.lower() == "pro":
    st.subheader("📈 PRO Analytics")
    col1, col2, col3 = st.columns(3)

    with col1:
        fig1 = px.bar(filtered_df.groupby("Make")["Price"].mean().reset_index(),
                      x="Make", y="Price", title="Average Price per Make")
        st.plotly_chart(fig1, use_container_width=True)
    with col2:
        fig2 = px.bar(filtered_df.groupby("Model").size().reset_index(name="Count"),
                      x="Model", y="Count", title="Listings per Model")
        st.plotly_chart(fig2, use_container_width=True)
    with col3:
        fig3 = px.line(filtered_df.groupby("Date")["Revenue"].sum().reset_index(),
                       x="Date", y="Revenue", title="Revenue Over Time")
        st.plotly_chart(fig3, use_container_width=True)

# ----------------------
# PLATINUM Charts + KPIs
# ----------------------
if user_plan.lower() == "platinum":
    st.subheader("🚀 Platinum Analytics")

    # --- Revenue Over Time ---
    fig_revenue = px.line(filtered_df.groupby("Date")["Revenue"].sum().reset_index(),
                          x="Date", y="Revenue", title="Revenue Over Time")
    st.plotly_chart(fig_revenue, use_container_width=True)

    # --- Listings Per Make ---
    fig_make = px.bar(filtered_df.groupby("Make").size().reset_index(name="Count"),
                      x="Make", y="Count", title="Listings per Make")
    st.plotly_chart(fig_make, use_container_width=True)

    # --- Average Price Per Make ---
    fig_price = px.bar(filtered_df.groupby("Make")["Price"].mean().reset_index(),
                       x="Make", y="Price", title="Average Price per Make")
    st.plotly_chart(fig_price, use_container_width=True)

    # --- Top 5 Models by Revenue ---
    top_models = filtered_df.groupby("Model")["Revenue"].sum().reset_index().sort_values("Revenue", ascending=False).head(5)
    fig_top_models = px.bar(top_models, x="Model", y="Revenue", title="Top 5 Models by Revenue")
    st.plotly_chart(fig_top_models, use_container_width=True)

    # --- Platform Performance ---
    platform_group = filtered_df.groupby("Platform")[["Reach","Impressions","Revenue"]].sum().reset_index()
    fig_platform = px.bar(platform_group, x="Platform", y=["Reach","Impressions","Revenue"],
                          title="Platform Performance", barmode="group")
    st.plotly_chart(fig_platform, use_container_width=True)

    # --- KPI Summary ---
    st.subheader("📌 Key Metrics")
    avg_price = int(filtered_df["Price"].mean()) if not filtered_df.empty else 0
    total_revenue = int(filtered_df["Revenue"].sum()) if not filtered_df.empty else 0
    posting_freq = round(filtered_df.groupby(filtered_df["Date"].dt.date).size().mean(), 1) if not filtered_df.empty else 0
    col1, col2, col3 = st.columns(3)
    col1.metric("Average Price", f"£{avg_price}")
    col2.metric("Total Revenue", f"£{total_revenue}")
    col3.metric("Avg Posting Frequency", f"{posting_freq} posts/day")

    # --- Recommendations ---
    st.subheader("💡 AI Recommendations")
    recs = platinum_recommendations(filtered_df)
    for r in recs:
        st.markdown(f"- {r}")

# ----------------------
# Footer note
# ----------------------
if demo_mode:
    st.info("⚠️ Charts shown above are demo data. Once you add listings, your real analytics will appear here.")
