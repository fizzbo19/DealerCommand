# frontend/pages/analytics_dashboard.py

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime
from backend.analytics import get_user_analytics_data, platinum_recommendations


# -----------------------------
# DEMO BADGE
# -----------------------------
def show_demo_badge():
    st.markdown(
        """
        <div style="
            background-color: #FFF3CD;
            border-left: 6px solid #FFCA2C;
            padding: 12px 20px;
            border-radius: 6px;
            margin-bottom: 15px;
        ">
            <strong>🧪 Demo Mode Enabled:</strong> You are currently viewing demo analytics.  
            Your real insights will appear automatically once you add listings.
        </div>
        """,
        unsafe_allow_html=True
    )


# -----------------------------
# DEMO DATA GENERATION
# -----------------------------
def load_demo_data():
    np.random.seed(42)
    demo_dates = pd.date_range(end=datetime.today(), periods=12, freq="M")
    return pd.DataFrame({
        "Date": demo_dates,
        "Revenue": np.random.randint(2000, 10000, size=12),
        "Reach": np.random.randint(5000, 20000, size=12),
        "Impressions": np.random.randint(10000, 40000, size=12),
        "Make": np.random.choice(["BMW", "Audi", "Mercedes", "Toyota"], size=12),
        "Model": np.random.choice(["X5", "A3", "C-Class", "Corolla"], size=12),
        "Platform": np.random.choice(["Facebook", "Instagram", "TikTok"], size=12),
        "Price": np.random.randint(20000, 50000, size=12),
        "Fuel": np.random.choice(["Petrol", "Diesel", "Hybrid"], size=12)
    })


# -----------------------------
# MAIN FUNCTION
# -----------------------------
def show_analytics_dashboard(user_email, user_plan):
    st.set_page_config(page_title="Analytics Dashboard | DealerCommand", layout="wide")
    st.title("📊 DealerCommand Analytics Dashboard")

    # -----------------------------
    # USER SESSION CHECK
    # -----------------------------
    if not user_email:
        st.warning("Please log in to view analytics.")
        st.stop()

    # -----------------------------
    # FETCH USER ANALYTICS DATA
    # -----------------------------
    analytics_df, use_demo_auto = get_user_analytics_data(user_email, user_plan.lower())

    # -----------------------------
    # DEMO MODE HANDLING
    # -----------------------------
    demo_mode = False
    if user_plan.lower() == "platinum":
        use_demo_toggle = st.checkbox("🧪 Show Demo Analytics", value=use_demo_auto)
        demo_mode = use_demo_toggle
    else:
        demo_mode = use_demo_auto

    # Replace with demo if empty or demo enabled
    if demo_mode or analytics_df.empty:
        analytics_df = load_demo_data()
        show_demo_badge()

    # -----------------------------
    # FILTERS
    # -----------------------------
    with st.expander("🔍 Filters"):
        makes = ["All"] + analytics_df["Make"].unique().tolist()
        models = ["All"] + analytics_df["Model"].unique().tolist()
        fuels = ["All"] + analytics_df["Fuel"].unique().tolist()

        selected_make = st.selectbox("Select Make", makes)
        selected_model = st.selectbox("Select Model", models)
        selected_fuel = st.selectbox("Fuel Type", fuels)

    filtered_df = analytics_df.copy()
    if selected_make != "All":
        filtered_df = filtered_df[filtered_df["Make"] == selected_make]
    if selected_model != "All":
        filtered_df = filtered_df[filtered_df["Model"] == selected_model]
    if selected_fuel != "All":
        filtered_df = filtered_df[filtered_df["Fuel"] == selected_fuel]

    # -----------------------------
    # DEMO-SPECIFIC SIMULATION
    # -----------------------------
    if demo_mode:
        st.subheader("🎛️ Demo Controls — Try Adjusting Your Stats")
        revenue_multiplier = st.slider("Simulate Revenue Multiplier", 0.5, 2.0, 1.0, 0.1)
        activity_multiplier = st.slider("Simulate Reach/Impressions Multiplier", 0.5, 2.0, 1.0, 0.1)

        filtered_df["Revenue"] = (filtered_df["Revenue"] * revenue_multiplier).astype(int)
        filtered_df["Reach"] = (filtered_df["Reach"] * activity_multiplier).astype(int)
        filtered_df["Impressions"] = (filtered_df["Impressions"] * activity_multiplier).astype(int)

    # -----------------------------
    # PRO ANALYTICS
    # -----------------------------
    if user_plan.lower() in ["pro", "platinum"]:
        st.subheader("📈 Pro Analytics")
        col1, col2, col3 = st.columns(3)

        with col1:
            fig1 = px.bar(
                filtered_df.groupby("Make")["Price"].mean().reset_index(),
                x="Make", y="Price", title="Average Price per Make"
            )
            st.plotly_chart(fig1, use_container_width=True)

        with col2:
            fig2 = px.bar(
                filtered_df.groupby("Model").size().reset_index(name="Count"),
                x="Model", y="Count", title="Listings per Model"
            )
            st.plotly_chart(fig2, use_container_width=True)

        with col3:
            fig3 = px.line(
                filtered_df.groupby("Date")["Revenue"].sum().reset_index(),
                x="Date", y="Revenue", title="Revenue Over Time"
            )
            st.plotly_chart(fig3, use_container_width=True)

    # -----------------------------
    # PLATINUM ANALYTICS
    # -----------------------------
    if user_plan.lower() == "platinum":
        st.subheader("🚀 Platinum Advanced Analytics")

        # Revenue Over Time
        fig_revenue = px.line(
            filtered_df.groupby("Date")["Revenue"].sum().reset_index(),
            x="Date", y="Revenue", title="Revenue Over Time"
        )
        st.plotly_chart(fig_revenue, use_container_width=True)

        # Listings per Make
        fig_make = px.bar(
            filtered_df.groupby("Make").size().reset_index(name="Count"),
            x="Make", y="Count", title="Listings per Make"
        )
        st.plotly_chart(fig_make, use_container_width=True)

        # Avg Price per Make
        fig_price = px.bar(
            filtered_df.groupby("Make")["Price"].mean().reset_index(),
            x="Make", y="Price", title="Average Price per Make"
        )
        st.plotly_chart(fig_price, use_container_width=True)

        # Top 5 Models by Revenue
        top_models = (
            filtered_df.groupby("Model")["Revenue"]
            .sum().reset_index()
            .sort_values("Revenue", ascending=False)
            .head(5)
        )
        fig_top_models = px.bar(
            top_models, x="Model", y="Revenue", title="Top 5 Models by Revenue"
        )
        st.plotly_chart(fig_top_models, use_container_width=True)

        # Platform Performance
        platform_stats = filtered_df.groupby("Platform")[["Reach", "Impressions", "Revenue"]].sum().reset_index()
        fig_platform = px.bar(
            platform_stats,
            x="Platform", y=["Reach", "Impressions", "Revenue"],
            barmode="group",
            title="Platform Performance Comparison"
        )
        st.plotly_chart(fig_platform, use_container_width=True)

        # KPIs
        st.subheader("📌 Key Metrics Summary")
        col_k1, col_k2, col_k3 = st.columns(3)
        col_k1.metric("Average Price", f"£{int(filtered_df['Price'].mean())}")
        col_k2.metric("Total Revenue", f"£{int(filtered_df['Revenue'].sum())}")
        col_k3.metric(
            "Avg Posting Frequency",
            f"{round(filtered_df.groupby(filtered_df['Date'].dt.date).size().mean(), 1)} posts/day"
        )

        # AI Recommendations
        st.subheader("💡 AI Insights & Recommendations")
        recs = platinum_recommendations(filtered_df)
        for r in recs:
            st.markdown(f"- {r}")

    # -----------------------------
    # FOOTER
    # -----------------------------
    if demo_mode:
        st.info("⚠️ You’re viewing demo data. Your real analytics will update automatically as you add listings.")
