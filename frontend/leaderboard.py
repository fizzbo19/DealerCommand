import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

# ----------------------------
# PAGE CONFIG
# ----------------------------
st.set_page_config(
    page_title="🏆 DealerCommand Leaderboard",
    page_icon="🚗",
    layout="wide"
)

# ----------------------------
# LOGO + BRANDING
# ----------------------------
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
LOGO_FILE = os.path.join(ASSETS_DIR, "dealercommand_logo.png")

col1, col2 = st.columns([1, 5])
with col1:
    if os.path.exists(LOGO_FILE):
        st.image(LOGO_FILE, width=120)
    else:
        st.markdown("### **DealerCommand AI**")

with col2:
    st.markdown("## 🏆 DealerCommand Leaderboard")
    st.markdown("_Celebrating top-performing dealerships leveraging AI for smarter listings._")

st.markdown("---")

# ----------------------------
# GOOGLE SHEETS SETUP
# ----------------------------
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

try:
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_service_account"], scope)
    client = gspread.authorize(creds)
except Exception as e:
    client = None
    st.warning("⚠️ Running in demo mode (no live data connection).")

# ----------------------------
# LOAD DATA
# ----------------------------
def get_sheet_data(sheet_name):
    try:
        sheet = client.open(sheet_name).sheet1
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()

sheet_name = "AI_Metrics"
df = get_sheet_data(sheet_name)

# ----------------------------
# FALLBACK DEMO DATA
# ----------------------------
if df.empty:
    st.info("Showing demo leaderboard data — real dealerships will appear here once onboarded 🚀")

    demo_data = pd.DataFrame({
        "Dealer": [
            "Autohaus Elite",
            "CarPlanet UK",
            "DrivePrime Ltd",
            "MotorMax Auto",
            "UrbanMotors"
        ],
        "Listings Generated": [57, 42, 36, 29, 25],
        "Avg Response Time (s)": [4.8, 5.2, 4.9, 5.6, 4.7],
        "AI Usage Score": [98, 90, 85, 80, 77],
        "Verified": ["✅ Yes"] * 5
    })

    st.dataframe(demo_data.style.highlight_max(subset=["Listings Generated"], color="#dbeafe"))

    chart = px.bar(
        demo_data,
        x="Dealer",
        y="Listings Generated",
        color="Listings Generated",
        text_auto=True,
        title="Top 5 Performing Dealerships (Demo Data)"
    )
    st.plotly_chart(chart, use_container_width=True)

else:
    st.success("✅ Live dealer data loaded from Google Sheets")

    # Clean up + summarize data
    df["Date"] = pd.to_datetime(df["Timestamp"]).dt.date
    dealer_stats = df.groupby("Email").agg({
        "Response Time (s)": "mean",
        "Prompt Length": "mean",
        "Timestamp": "count"
    }).reset_index()

    dealer_stats.rename(columns={
        "Email": "Dealer",
        "Timestamp": "Listings Generated",
        "Response Time (s)": "Avg Response Time (s)",
        "Prompt Length": "Avg Prompt Length"
    }, inplace=True)

    dealer_stats["AI Usage Score"] = round(
        100 - dealer_stats["Avg Response Time (s)"] + (dealer_stats["Listings Generated"] / dealer_stats["Listings Generated"].max()) * 10, 1
    )

    dealer_stats.sort_values("Listings Generated", ascending=False, inplace=True)

    st.dataframe(dealer_stats.style.highlight_max(subset=["Listings Generated"], color="#dbeafe"))

    chart = px.bar(
        dealer_stats.head(10),
        x="Dealer",
        y="Listings Generated",
        color="Listings Generated",
        text_auto=True,
        title="Top 10 Dealers Using DealerCommand AI"
    )
    st.plotly_chart(chart, use_container_width=True)

# ----------------------------
# FOOTER
# ----------------------------
st.markdown("---")
st.markdown(
    "<p style='text-align:center;'>🚗 Powered by <strong>DealerCommand AI</strong> | Transforming Dealerships with Smart Automation</p>",
    unsafe_allow_html=True
)
