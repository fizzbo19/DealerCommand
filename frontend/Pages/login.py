# frontend/pages/1_Login.py
import sys, os, re
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
from backend.sheet_utils import append_to_google_sheet, get_sheet_data
from backend.auth_utils import hash_password, verify_password
from backend.email_utils import send_reset_email  # We'll create this simple utility

# -------------------------
# SOCIAL AUTH (Google / Microsoft)
# -------------------------
from streamlit_oauth import OAuth2Component

GOOGLE_CLIENT_ID = st.secrets["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = st.secrets["GOOGLE_CLIENT_SECRET"]

MICROSOFT_CLIENT_ID = st.secrets["MICROSOFT_CLIENT_ID"]
MICROSOFT_CLIENT_SECRET = st.secrets["MICROSOFT_CLIENT_SECRET"]

google_oauth = OAuth2Component(
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    authorize_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint="https://oauth2.googleapis.com/token",
    redirect_uri="http://localhost:8501/",
    scopes=["openid","email","profile"]
)

ms_oauth = OAuth2Component(
    client_id=MICROSOFT_CLIENT_ID,
    client_secret=MICROSOFT_CLIENT_SECRET,
    authorize_endpoint="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    token_endpoint="https://login.microsoftonline.com/common/oauth2/v2.0/token",
    redirect_uri="http://localhost:8501/",
    scopes=["User.Read"]
)

st.set_page_config(page_title="Login | DealerCommand", layout="centered")
st.header("🔐 Login / Sign Up")

# -----------------------
# PHONE VALIDATION FUNCTION
# -----------------------
def is_valid_phone(phone):
    """
    Validates UK phone numbers.
    Accepts formats: 07123..., +447123...
    """
    pattern = r"^(?:\+44|0)\d{10}$"
    return re.match(pattern, phone)

# ============================
# LOGIN & SIGNUP TABS
# ============================
tab1, tab2, tab3 = st.tabs(["🔑 Login", "📝 Sign Up", "🔄 Forgot Password"])

# ----------------------------------
# 🔑 LOGIN TAB
# ----------------------------------
with tab1:
    st.subheader("Login")
    login_email = st.text_input("Email")
    login_password = st.text_input("Password", type="password")

    if st.button("Login"):
        sheet = get_sheet_data("Dealership_Profiles")
        user_row = sheet[sheet["Email"].str.lower() == login_email.lower()]

        if user_row.empty:
            st.error("Account not found.")
        else:
            saved_hash = user_row.iloc[0]["Password_Hash"]
            if verify_password(login_password, saved_hash):
                st.success("Login successful!")
                st.session_state["authenticated"] = True
                st.session_state["user_email"] = login_email
                st.experimental_rerun()
            else:
                st.error("Incorrect password.")

    st.markdown("---")
    st.write("Or continue using:")
    google_oauth.authorize_button("Continue with Google")
    ms_oauth.authorize_button("Continue with Microsoft")

# ----------------------------------
# 📝 SIGN-UP TAB
# ----------------------------------
with tab2:
    st.subheader("Create Account")

    with st.form("signup_form"):
        email = st.text_input("Email *")
        password = st.text_input("Password *", type="password")
        dealer_name = st.text_input("Dealership Name *")
        dealer_phone = st.text_input("Phone Number *")
        dealer_location = st.text_input("Location / City *")
        dealer_website = st.text_input("Website (optional)")
        dealer_size = st.selectbox("Dealership Size *", [
            "1–5 cars", "6–20 cars", "21–50 cars", "50+ cars"
        ])
        dealer_postcode = st.text_input("Postcode *")

        signup_submit = st.form_submit_button("Create Account")

        if signup_submit:
            # -----------------------
            # CHECK REQUIRED FIELDS
            # -----------------------
            if not all([email, password, dealer_name, dealer_phone, dealer_location, dealer_size, dealer_postcode]):
                st.error("Please fill all required fields (*)")
                st.stop()

            # -----------------------
            # PHONE VALIDATION
            # -----------------------
            if not is_valid_phone(dealer_phone):
                st.error("Phone number must be a valid UK number (07123..., +447123...).")
                st.stop()

            # -----------------------
            # SAVE TO SHEET
            # -----------------------
            append_to_google_sheet("Dealership_Profiles", {
                "Email": email,
                "Password_Hash": hash_password(password),
                "Dealership_Name": dealer_name,
                "Phone": dealer_phone,
                "Location": dealer_location,
                "Website": dealer_website,
                "Size": dealer_size,
                "Postcode": dealer_postcode
            })
            st.success("✅ Account created! You can now log in.")

# ----------------------------------
# 🔄 FORGOT PASSWORD TAB
# ----------------------------------
with tab3:
    st.subheader("Reset Password")
    reset_email = st.text_input("Enter your email to reset password")

    if st.button("Send Reset Email"):
        sheet = get_sheet_data("Dealership_Profiles")
        user_row = sheet[sheet["Email"].str.lower() == reset_email.lower()]

        if user_row.empty:
            st.error("No account found with this email.")
        else:
            # Send reset email via simple utility
            send_reset_email(reset_email)
            st.success(f"✅ Password reset email sent to {reset_email}. Please check your inbox.")
