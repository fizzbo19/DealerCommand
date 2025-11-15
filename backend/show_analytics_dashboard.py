# backend/analytics_dashboard.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime
from io import BytesIO

from backend.analytics import get_user_analytics_data, platinum_recommendations

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

def fig_to_png(fig):
    # Requires python package 'kaleido'
    try:
        return fig.to_image(format="png")
    except Exception:
        return None

# -----------------------------
# Main function (callable)
# -----------------------------
def show_analytics_dashboard(user_email, user_plan):
    st.set_page_config(page_title="Analytics Dashboard | DealerCommand", layout="wide")
    st.title("📊 DealerCommand Analytics")

    analytics_df, use_demo_auto = get_user_analytics_data(user_email, user_plan.lower())

    # Demo toggle for platinum only
    demo_mode = False
    if user_plan.lower() == "platinum":
        demo_mode = st.checkbox("🧪 Show Demo Analytics (Platinum)", value=use_demo_auto)
    else:
        demo_mode = use_demo_auto

    if demo_mode or analytics_df.empty:
        analytics_df = load_demo_data()
        show_demo_badge()

    # Ensure types
    if "Date" in analytics_df.columns:
        analytics_df["Date"] = pd.to_datetime(analytics_df["Date"], errors="coerce")
    if "Price" in analytics_df.columns:
        analytics_df["Price"] = pd.to_numeric(analytics_df["Price"], errors="coerce").fillna(0)
    if "Revenue" in analytics_df.columns:
        analytics_df["Revenue"] = pd.to_numeric(analytics_df["Revenue"], errors="coerce").fillna(0)

    # Filters
    with st.expander("🔍 Filters"):
        makes = ["All"] + analytics_df["Make"].dropna().unique().tolist()
        selected_make = st.selectbox("Make", makes)
        models = ["All"] + analytics_df["Model"].dropna().unique().tolist()
        selected_model = st.selectbox("Model", models)
        platforms = ["All"] + analytics_df["Platform"].dropna().unique().tolist()
        selected_platform = st.selectbox("Platform", platforms)
        date_range = st.date_input("Date Range", [analytics_df["Date"].min().date(), analytics_df["Date"].max().date()]) if not analytics_df.empty else None

    filtered = analytics_df.copy()
    if selected_make != "All":
        filtered = filtered[filtered["Make"] == selected_make]
    if selected_model != "All":
        filtered = filtered[filtered["Model"] == selected_model]
    if selected_platform != "All":
        filtered = filtered[filtered["Platform"] == selected_platform]
    if date_range:
        start_dt, end_dt = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
        filtered = filtered[(filtered["Date"] >= start_dt) & (filtered["Date"] <= end_dt)]

    # Top-row KPIs
    st.subheader("📌 Key Metrics")
    k0, k1, k2, k3 = st.columns(4)
    total_revenue = int(filtered["Revenue"].sum()) if not filtered.empty else 0
    avg_price = int(filtered["Price"].mean()) if not filtered.empty else 0
    total_listings = len(filtered)
    avg_reach = int(filtered["Reach"].mean()) if "Reach" in filtered.columns and not filtered.empty else 0
    k0.metric("Total Revenue", f"£{total_revenue}")
    k1.metric("Average Price", f"£{avg_price}")
    k2.metric("Listings", f"{total_listings}")
    k3.metric("Avg Reach", f"{avg_reach}")

    # CSV export
    csv_bytes = df_to_csv_bytes(filtered)
    st.download_button("⬇ Download filtered data (CSV)", csv_bytes, file_name="analytics_filtered.csv", mime="text/csv")

    # -------------------------
    # Charts area
    # -------------------------
    st.markdown("### Revenue & Listings")
    c1, c2 = st.columns([2,1])

    # Revenue over time (monthly)
    rev_df = filtered.groupby(pd.Grouper(key="Date", freq="M"))["Revenue"].sum().reset_index()
    if rev_df.empty:
        st.info("No data to display for selected filters.")
    else:
        fig_rev = px.line(rev_df, x="Date", y="Revenue", title="Revenue Over Time (Monthly)")
        c1.plotly_chart(fig_rev, use_container_width=True)

        # cumulative revenue
        rev_df["Cumulative"] = rev_df["Revenue"].cumsum()
        fig_cum = px.area(rev_df, x="Date", y="Cumulative", title="Cumulative Revenue")
        c1.plotly_chart(fig_cum, use_container_width=True)

    # Price distribution
    if not filtered.empty and "Price" in filtered.columns:
        fig_price = px.histogram(filtered, x="Price", nbins=20, title="Price Distribution")
        c2.plotly_chart(fig_price, use_container_width=True)

    # Platform performance
    if "Platform" in filtered.columns:
        st.markdown("### Platform Performance")
        pf = filtered.groupby("Platform")[["Reach","Impressions","Revenue"]].sum().reset_index()
        fig_pf = px.bar(pf, x="Platform", y=["Reach","Impressions","Revenue"], barmode="group", title="Platform Comparison")
        st.plotly_chart(fig_pf, use_container_width=True)

    # Top models by revenue
    st.markdown("### Top Models")
    if "Model" in filtered.columns:
        top_models = filtered.groupby("Model")["Revenue"].sum().reset_index().sort_values("Revenue", ascending=False).head(10)
        st.dataframe(top_models)

    # Recommendations (Platinum)
    if user_plan.lower() == "platinum":
        st.markdown("### 💡 AI Recommendations")
        recs = platinum_recommendations(filtered)
        for r in recs:
            st.markdown(f"- {r}")

    # Download a chart as PNG (best-effort)
    try:
        img = fig_rev.to_image(format="png")
        st.download_button("⬇ Download Revenue chart (PNG)", img, file_name="revenue_chart.png", mime="image/png")
    except Exception:
        st.info("To download charts as PNG install 'kaleido' in your environment.")

    # Footer demo notice
    if demo_mode:
        st.info("⚠️ Demo data shown. Real analytics update when you add listings.")
