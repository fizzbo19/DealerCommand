import streamlit as st
from backend.stripe_utils import create_checkout_session

email = st.session_state.get("user_email")
if not email:
    st.warning("Please login first.")
    st.stop()

st.title("💳 Billing & Subscription")

st.markdown("Your current plan: **Starter / Pro / Premium** (placeholder)")

if st.button("Upgrade Plan"):
    url = create_checkout_session(email, plan="pro")
    st.markdown(f"[Go to Checkout]({url})", unsafe_allow_html=True)
