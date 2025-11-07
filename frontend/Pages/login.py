# frontend/pages/1_Login.py
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
from backend.trial_manager import ensure_user_and_get_status

st.set_page_config(page_title="Login | DealerCommand", layout="centered")
st.header("🔐 Login / Sign Up")

email = st.text_input("Dealership email")

if st.button("Continue"):
    if not email:
        st.warning("Please enter your email.")
    else:
        try:
            status, expiry, used = ensure_user_and_get_status(email)
            st.session_state["authenticated"] = True
            st.session_state["user_email"] = email
            if status == "new":
                st.success("Welcome — your 3-month trial has started.")
            elif status == "active":
                st.success(f"Welcome back — trial active until {expiry}.")
            else:
                st.error("Your trial has expired. Please upgrade.")
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Backend error: {e}")
