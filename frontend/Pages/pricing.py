# frontend/pages/5_Pricing.py
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
from backend.trial_manager import get_trial_status
from backend.stripe_utils import create_checkout_session

st.set_page_config(page_title="Pricing", layout="wide")

if not st.session_state.get("authenticated"):
    st.warning("Please login first.")
    st.stop()

email = st.session_state.get("user_email")
status, expiry, used = get_trial_status(email)

st.title("💰 Pricing Plans")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Pro")
    st.write("£9.99 / month — up to 15 listings per month")
    if st.button("Choose Pro"):
        url = create_checkout_session("price_xxxxx_pro", email)
        if url:
            st.markdown(f"[Proceed to Checkout]({url})")
        else:
            st.info("Checkout not configured — set Stripe keys & price IDs in environment.")

with col2:
    st.subheader("Premium")
    st.write("£24.99 / month — unlimited listings, priority support")
    if st.button("Choose Premium"):
        url = create_checkout_session("price_xxxxx_premium", email)
        if url:
            st.markdown(f"[Proceed to Checkout]({url})")
        else:
            st.info("Checkout not configured.")
