# backend/analytics_dashboard.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime

from backend.analytics import get_user_analytics_data, platinum_recommendations
from backend.trial_manager import ensure_user_and_get_status

# -----------------------------
# Helpers
# -----------------------------
def show_demo_badge():
    st.markdown(
        """<div style="
            background-color: #FFF3CD;
            border-left: 6px solid #FFCA2C;
            padding:12px 20px; border-radius:6px; margin-bottom:15px;">
            <strong>🧪 Demo Mode Enabled:</strong> Viewing demo analytics. Real data appears after you add listings.
        </div>""", unsafe_allow_html=True
    )

def load_demo_data():
    np.random.seed(42)
    demo_dates = pd.date_range(end=datetime.today(), periods=12, freq="M")
    return pd.DataFrame({
        "Date": demo_dates,
        "Revenue": np.random.randint(2000, 10000, size=12),
        "Reach": np.random.randint(5000, 20000, size=12),
        "Impressions": np.random.randint(10000, 40000, size=12),
        "Make": np.random.choice(["BMW","Audi","Mercedes","Toyota"], size=12),
        "Model": np.random.choice(["X5","A3","C-Class","Corolla"], size=12),
        "Platform": np.random.choice(["Facebook","Instagram","TikTok"], size=12),
        "Price": np.random.randint(20000,50000, size=12),
        "Fuel": np.random.choice(["Petrol","Diesel","Hybrid"], size=12)
    })

def df_to_csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8")

def get_filtered_data(df, make, model, platform, date_range):
    filtered = df.copy()
    if make != "All":
        filtered = filtered[filtered["Make"] == make]
    if model != "All":
        filtered = filtered[filtered["Model"] == model]
    if platform != "All":
        filtered = filtered[filtered["Platform"] == platform]
    if date_range:
        start_dt, end_dt = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
        filtered = filtered[(filtered["Date"] >= start_dt) & (filtered["Date"] <= end_dt)]
    return filtered

def calculate_kpis(df):
    if df.empty:
        return {"total_revenue":0, "avg_price":0, "total_listings":0, "avg_reach":0}
    return {
        "total_revenue": int(df["Revenue"].sum()),
        "avg_price": int(df["Price"].mean()),
        "total_listings": len(df),
        "avg_reach": int(df["Reach"].mean()) if "Reach" in df.columns else 0
    }

def plot_revenue_charts(df):
    rev_df = df.groupby(pd.Grouper(key="Date", freq="M"))["Revenue"].sum().reset_index()
    if rev_df.empty:
        return None, None
    rev_fig = px.line(rev_df, x="Date", y="Revenue", title="Revenue Over Time (Monthly)")
    rev_df["Cumulative"] = rev_df["Revenue"].cumsum()
    cum_fig = px.area(rev_df, x="Date", y="Cumulative", title="Cumulative Revenue")
    return rev_fig, cum_fig

# -----------------------------
# Main function
# -----------------------------
def show_analytics_dashboard(user_email):
    st.set_page_config(page_title="Analytics Dashboard | DealerCommand", layout="wide")
    st.title("📊 DealerCommand Analytics")

    # -----------------------------
    # Determine trial / plan status
    # -----------------------------
    status, expiry, _, _, plan = ensure_user_and_get_status(user_email)
    is_trial_active = status == "active" and plan.lower() == "free trial"
    effective_plan = "platinum" if is_trial_active else plan.lower()

    # -----------------------------
    # Fetch analytics
    # -----------------------------
    analytics_df, use_demo_auto = get_user_analytics_data(user_email, effective_plan)

    # Demo mode logic
    demo_mode = False
    if effective_plan == "platinum":
        demo_mode = st.checkbox("🧪 Show Demo Analytics (Platinum)", value=use_demo_auto)
    else:
        demo_mode = use_demo_auto

    if demo_mode or analytics_df.empty:
        analytics_df = load_demo_data()
        show_demo_badge()

    # Ensure correct types
    for col in ["Date", "Price", "Revenue"]:
        if col in analytics_df.columns:
            if col == "Date":
                analytics_df[col] = pd.to_datetime(analytics_df[col], errors="coerce")
            else:
                analytics_df[col] = pd.to_numeric(analytics_df[col], errors="coerce").fillna(0)

    # -----------------------------
    # Filters
    # -----------------------------
    with st.expander("🔍 Filters"):
        makes = ["All"] + analytics_df["Make"].dropna().unique().tolist()
        selected_make = st.selectbox("Make", makes)
        models = ["All"] + analytics_df["Model"].dropna().unique().tolist()
        selected_model = st.selectbox("Model", models)
        platforms = ["All"] + analytics_df["Platform"].dropna().unique().tolist()
        selected_platform = st.selectbox("Platform", platforms)
        date_range = st.date_input(
            "Date Range", 
            [analytics_df["Date"].min().date(), analytics_df["Date"].max().date()]
        ) if not analytics_df.empty else None

    filtered_df = get_filtered_data(analytics_df, selected_make, selected_model, selected_platform, date_range)

    # -----------------------------
    # KPIs
    # -----------------------------
    st.subheader("📌 Key Metrics")
    kpis = calculate_kpis(filtered_df)
    k0, k1, k2, k3 = st.columns(4)
    k0.metric("Total Revenue", f"£{kpis['total_revenue']}")
    k1.metric("Average Price", f"£{kpis['avg_price']}")
    k2.metric("Listings", f"{kpis['total_listings']}")
    k3.metric("Avg Reach", f"{kpis['avg_reach']}")

    # CSV export
    st.download_button("⬇ Download filtered data (CSV)", df_to_csv_bytes(filtered_df),
                       file_name="analytics_filtered.csv", mime="text/csv")

    # -----------------------------
    # Charts
    # -----------------------------
    st.markdown("### Revenue & Listings")
    c1, c2 = st.columns([2,1])
    rev_fig, cum_fig = plot_revenue_charts(filtered_df)
    if rev_fig:
        c1.plotly_chart(rev_fig, use_container_width=True)
        c1.plotly_chart(cum_fig, use_container_width=True)
        try:
            img = rev_fig.to_image(format="png")
            st.download_button("⬇ Download Revenue chart (PNG)", img, file_name="revenue_chart.png", mime="image/png")
        except Exception:
            st.info("To download charts as PNG install 'kaleido'.")

    # Price distribution
    if not filtered_df.empty and "Price" in filtered_df.columns:
        fig_price = px.histogram(filtered_df, x="Price", nbins=20, title="Price Distribution")
        c2.plotly_chart(fig_price, use_container_width=True)

    # Platform performance
    if "Platform" in filtered_df.columns:
        st.markdown("### Platform Performance")
        pf = filtered_df.groupby("Platform")[["Reach","Impressions","Revenue"]].sum().reset_index()
        fig_pf = px.bar(pf, x="Platform", y=["Reach","Impressions","Revenue"], barmode="group", title="Platform Comparison")
        st.plotly_chart(fig_pf, use_container_width=True)

    # Top models by revenue
    st.markdown("### Top Models")
    if "Model" in filtered_df.columns:
        top_models = filtered_df.groupby("Model")["Revenue"].sum().reset_index().sort_values("Revenue", ascending=False).head(10)
        st.dataframe(top_models)

    # Platinum recommendations
    if effective_plan == "platinum":
        st.markdown("### 💡 AI Recommendations")
        recs = platinum_recommendations(filtered_df)
        for r in recs:
            st.markdown(f"- {r}")

    # Footer notice for demo/trial
    if demo_mode or is_trial_active:
        st.info("⚠️ Demo data or trial Platinum access shown. Real analytics update when you add listings or your trial ends.")

