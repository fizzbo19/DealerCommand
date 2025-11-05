# frontend/pages/2_Dashboard.py
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import datetime
from backend.trial_manager import get_trial_status, get_recent_user_listings

st.set_page_config(page_title="Dashboard | DealerCommand", layout="wide")

if not st.session_state.get("authenticated"):
    st.warning("Please login first on the Login page.")
    st.stop()

email = st.session_state.get("user_email")
status, expiry, used = get_trial_status(email)

st.title("📊 Dashboard")
st.markdown(f"**Account**: {email}")
col1, col2, col3 = st.columns(3)
col1.metric("Trial status", status.capitalize())
col2.metric("Trial ends", str(expiry) if expiry else "—")
col3.metric("Listings used", used)

st.markdown("---")
st.header("Recent Listings")
recent = get_recent_user_listings(email, limit=8)
if recent:
    for r in recent:
        with st.expander(f"{r.get('Date','')} • {r.get('Car','-')[:40]}"):
            st.write("Tone:", r.get("Tone","-"))
            st.write(r.get("Listing","-"))
else:
    st.info("No recent listings saved yet.")

