import streamlit as st
from datetime import datetime
import pandas as pd
from urllib.parse import parse_qs, urlparse
import sys
import os

# -----------------------------
# PATH SETUP
# -----------------------------
# Ensure backend directory is accessible for local imports
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.extend([BASE_DIR, BACKEND_DIR])

# -----------------------------
# LOCAL IMPORTS
# -----------------------------
# Import the Stripe utility function we need
from backend.stripe_utils import get_subscription_details
# Import sheet utils to potentially update the user profile after payment (Fulfillment step)
from backend.sheet_utils import save_dealership_profile

# -----------------------------
# PAGE CONFIG
# -----------------------------
st.set_page_config(page_title="DealerCommand - Subscription Activated", page_icon="✅")

# --- 1. GET SESSION ID FROM URL ---
# Streamlit runs in an iframe, and URL access can be tricky. We simulate getting the URL parameters.
# In a real deployed environment, you might need JavaScript or a dedicated server route to get the URL parameters.
# For Streamlit's local testing, we rely on st.query_params, though it can be inconsistent depending on deployment.

query_params = st.query_params
session_id = query_params.get("session_id")

# --- 2. INITIALIZE VARIABLES ---
DEFAULT_EMAIL = "Subscription Not Found"
DEFAULT_PLAN = "Free Trial"
DEFAULT_DATE = datetime.now().strftime("%B %d, %Y")

subscription_email = DEFAULT_EMAIL
subscription_plan = DEFAULT_PLAN
subscription_date = DEFAULT_DATE
fulfillment_status = "Pending"

# --- 3. FETCH DETAILS FROM STRIPE (if session_id exists) ---
if session_id:
    st.info(f"Retrieving details for session ID: {session_id}")
    details = get_subscription_details(session_id)
    
    if details and details.get("status") == "active":
        
        # Extract Subscription Details
        subscription_email = details.get("customer_email", DEFAULT_EMAIL)
        # Use the plan_upgrade metadata we passed during checkout
        subscription_plan = details.get("metadata", {}).get("plan_upgrade", DEFAULT_PLAN).capitalize()
        subscription_date = datetime.now().strftime("%B %d, %Y")
        
        # --- 4. FULFILLMENT: UPDATE BACKEND PROFILE (Critical Step) ---
        try:
            # When the subscription is active, update the user's plan permanently in the Google Sheet.
            save_dealership_profile(subscription_email, {
                "Plan": subscription_plan,
                "Trial_Status": "active", # Mark trial as active/paid
                # We do NOT reset the trial dates here, just update the plan tier
            })
            fulfillment_status = "Profile Updated"
        except Exception as e:
            fulfillment_status = f"Fulfillment Failed: {e}"
            st.error(f"⚠️ FULFILLMENT ERROR: Failed to update database for {subscription_email}.")
            
    else:
        st.warning("Could not retrieve active subscription details for this session ID.")
        subscription_email = DEFAULT_EMAIL
        subscription_plan = DEFAULT_PLAN
        fulfillment_status = "Error/Inactive"

# -----------------------------
# DISPLAY SUCCESS PAGE
# -----------------------------

st.title("🎉 Subscription Activated Successfully!")

st.markdown("""
### Thank you for upgrading to **DealerCommand**!
Your subscription is now active, and you have full access to all premium features.
""")

st.markdown(f"""
<div style="padding: 15px; border: 1px solid #4CAF50; border-radius: 10px; background-color: #e8f5e9;">
    <h4>Subscription Summary:</h4>
    <p><strong>👤 Account Email:</strong> <code>{subscription_email}</code></p>
    <p><strong>💼 Purchased Plan:</strong> <strong>{subscription_plan}</strong></p>
    <p><strong>📅 Activation Date:</strong> {subscription_date}</p>
    <p><strong>💾 Fulfillment Status:</strong> {fulfillment_status}</p>
</div>
""", unsafe_allow_html=True)

st.divider()

st.markdown("""
### 🚀 Next Steps
- Head back to your dashboard to start exploring your upgraded tools.  
- Your new features are now fully unlocked, including unlimited AI listings, advanced analytics, and custom reporting.  
- You’ll also receive a confirmation email from Stripe with your payment receipt.
""")

st.success(f"You're all set to supercharge your dealership with the {subscription_plan} plan!")

st.page_link("app.py", label="⬅️ Return to Dashboard", icon="🏠")

st.markdown("---")
st.markdown("💬 Need help? [Contact support](mailto:info@dealercommand.tech)")