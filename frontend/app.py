# frontend/app.py
import sys, os, json
from datetime import datetime, date
import streamlit as st
from openai import OpenAI

# Local imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.trial_manager import ensure_user_and_get_status, increment_usage
from backend.sheet_utils import append_to_google_sheet
from backend.stripe_utils import create_checkout_session

# Optional animations
try:
    from streamlit_lottie import st_lottie
except ImportError:
    st_lottie = None

# ----------------------
# PAGE CONFIG
# ----------------------
st.set_page_config(
    page_title="DealerCommand AI | Smart Automotive Listings",
    layout="wide",
    page_icon="🚗"
)

# ----------------------
# SESSION STATE
# ----------------------
if "theme" not in st.session_state:
    st.session_state.theme = "light"

# ----------------------
# ASSETS & LOGO HANDLING
# ----------------------
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
LOGO_FILE = os.path.join(ASSETS_DIR, "dealercommand_logov1.png")

def render_logo_sidebar():
    if os.path.exists(LOGO_FILE):
        st.sidebar.image(LOGO_FILE, width=160)
    else:
        st.sidebar.markdown("**DealerCommand AI**")

# ----------------------
# THEME TOGGLE
# ----------------------
def toggle_theme():
    st.session_state.theme = "dark" if st.session_state.theme == "light" else "light"

theme_bg = "#0f172a" if st.session_state.theme == "dark" else "#f9fafb"
theme_text = "#f9fafb" if st.session_state.theme == "dark" else "#111827"
theme_secondary = "#94a3b8" if st.session_state.theme == "dark" else "#6b7280"
card_bg = "rgba(255,255,255,0.08)" if st.session_state.theme == "dark" else "#ffffff"
shadow_color = "rgba(255,255,255,0.1)" if st.session_state.theme == "dark" else "rgba(0,0,0,0.1)"

# ----------------------
# CUSTOM CSS
# ----------------------
st.markdown(f"""
<style>
body {{
    background-color: {theme_bg};
    color: {theme_text};
    font-family: 'Inter', sans-serif;
}}
.hero-title {{
    font-size: 2.2rem;
    font-weight: 700;
    text-align: center;
    color: {theme_text};
    margin-bottom: 0.4rem;
}}
.hero-sub {{
    text-align: center;
    color: {theme_secondary};
    font-size: 1.05rem;
    margin-bottom: 2rem;
}}
.stButton > button {{
    background: linear-gradient(90deg, #2563eb, #1e40af);
    color: white;
    border-radius: 10px;
    padding: 0.6rem 1.4rem;
    font-weight: 600;
    border: none;
    box-shadow: 0 2px 8px {shadow_color};
    transition: 0.2s ease-in-out;
}}
.stButton > button:hover {{
    background: linear-gradient(90deg, #1e40af, #2563eb);
    transform: scale(1.02);
}}
.card {{
    background: {card_bg};
    border-radius: 16px;
    box-shadow: 0 4px 10px {shadow_color};
    padding: 1.4rem;
    text-align: center;
    margin-bottom: 1rem;
}}
.card h3 {{
    margin-bottom: 0.4rem;
    font-size: 1.1rem;
}}
.card p {{
    font-size: 1.6rem;
    font-weight: 700;
}}
.footer {{
    text-align: center;
    color: {theme_secondary};
    font-size: 0.9rem;
    margin-top: 3rem;
}}
.toast {{
    background-color: #10b981;
    color: white;
    padding: 12px 16px;
    border-radius: 10px;
    text-align: center;
    margin: 15px 0;
    font-weight: 600;
    box-shadow: 0 2px 6px rgba(0,0,0,0.2);
}}
</style>
""", unsafe_allow_html=True)

# ----------------------
# NAVIGATION
# ----------------------
col_toggle = st.sidebar.columns([3, 1])
with col_toggle[0]:
    st.sidebar.markdown("## 🧭 Navigation")
page = st.sidebar.radio("Go to", ["🏠 Home", "📊 Dashboard", "🧾 Generate Listing", "💳 Billing", "📞 Support"])
with col_toggle[1]:
    st.sidebar.button("🌗", on_click=toggle_theme)

st.sidebar.markdown("---")
render_logo_sidebar()

# ----------------------
# HOME PAGE
# ----------------------
if page == "🏠 Home":
    st.markdown(f"""
    <div style='text-align:center;'>
        <h1 class="hero-title">🚗 DealerCommand AI</h1>
        <p class="hero-sub">
            The smarter way to create SEO-optimised, high-converting automotive listings in seconds.
        </p>
        <img src="https://cdn-icons-png.flaticon.com/512/743/743131.png" width="80">
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 🔍 Key Features")
    st.markdown(f"""
    - 🧠 AI-powered vehicle listing generation  
    - ⚡ Instant SEO-optimised content  
    - 📈 Track your usage and upgrade anytime  
    - 🧾 Export listings to share or post online
    """)

    st.markdown("---")
    st.info("👋 Enter your dealership email in the 'Generate Listing' tab to begin your free trial.")

# ----------------------
# DASHBOARD PAGE
# ----------------------
elif page == "📊 Dashboard":
    st.markdown("## 📊 Dashboard Overview")

    user_email = st.text_input("Enter your dealership email:", placeholder="e.g. sales@autohub.co.uk")

    if user_email:
        status, expiry, usage_count = ensure_user_and_get_status(user_email)
        is_active = status in ["active", "new"]
        plan = "🚀 Pro Plan" if status == "active" else "🧪 Free Trial"
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date() if expiry else None
        days_left = (expiry_date - date.today()).days if expiry_date else 0
        usage_percent = min((usage_count / 15) * 100, 100)

        col1, col2, col3, col4 = st.columns(4)
        col1.markdown(f"<div class='card'><h3>📦 Total Listings</h3><p>{usage_count}</p></div>", unsafe_allow_html=True)
        col2.markdown(f"<div class='card'><h3>🕓 Days Left</h3><p>{days_left if days_left > 0 else 0}</p></div>", unsafe_allow_html=True)
        col3.markdown(f"<div class='card'><h3>💳 Plan</h3><p>{plan}</p></div>", unsafe_allow_html=True)
        col4.markdown(f"<div class='card'><h3>📈 Usage</h3><p>{int(usage_percent)}%</p></div>", unsafe_allow_html=True)

        st.progress(int(usage_percent))
        if not is_active:
            st.warning("⚠️ Your trial has ended — upgrade to continue generating listings.")
            if st.button("💳 Upgrade to Pro"):
                checkout_url = create_checkout_session(user_email)
                st.markdown(f"[👉 Upgrade Now]({checkout_url})", unsafe_allow_html=True)

# ----------------------
# GENERATE LISTING PAGE
# ----------------------
elif page == "🧾 Generate Listing":
    st.markdown("### ✨ Generate a New Car Listing")

    user_email = st.text_input("📧 Dealership email", placeholder="e.g. sales@autohub.co.uk")
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        st.error("⚠️ Missing OpenAI key — set `OPENAI_API_KEY` in Render environment.")
        st.stop()

    if user_email:
        status, expiry, usage_count = ensure_user_and_get_status(user_email)
        is_active = status in ["active", "new"]

        if is_active:
            st.caption("Complete the details below and let AI handle the rest.")
            with st.form("listing_form"):
                col1, col2 = st.columns(2)
                with col1:
                    make = st.text_input("Car Make", "BMW")
                    model = st.text_input("Model", "X5 M Sport")
                    year = st.text_input("Year", "2021")
                    mileage = st.text_input("Mileage", "28,000 miles")
                    color = st.text_input("Color", "Black")
                with col2:
                    fuel = st.selectbox("Fuel Type", ["Petrol", "Diesel", "Hybrid", "Electric"])
                    transmission = st.selectbox("Transmission", ["Automatic", "Manual"])
                    price = st.text_input("Price", "£45,995")
                    features = st.text_area("Key Features", "Panoramic roof, heated seats, M Sport package")
                    notes = st.text_area("Dealer Notes (optional)", "Full service history, finance available")

                submitted = st.form_submit_button("🚀 Generate Listing")

            if submitted:
                try:
                    client = OpenAI(api_key=api_key)
                    prompt = f"""
You are an expert automotive marketing assistant.
Write a professional, engaging listing for this car:

Make: {make}
Model: {model}
Year: {year}
Mileage: {mileage}
Color: {color}
Fuel: {fuel}
Transmission: {transmission}
Price: {price}
Features: {features}
Dealer Notes: {notes}

Guidelines:
- 100–150 words
- Emphasise the car’s best features
- Add relevant emojis
- Optimised for online car marketplaces
"""
                    with st.spinner("🤖 Generating your listing..."):
                        response = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {"role": "system", "content": "You are a top-tier automotive copywriter."},
                                {"role": "user", "content": prompt},
                            ],
                            temperature=0.7,
                        )
                        listing = response.choices[0].message.content.strip()

                    increment_usage(user_email, listing)
                    car_data = {
                        "Make": make, "Model": model, "Year": year, "Mileage": mileage,
                        "Color": color, "Fuel Type": fuel, "Transmission": transmission,
                        "Price": price, "Features": features, "Dealer Notes": notes
                    }
                    append_to_google_sheet(user_email, car_data)

                    st.markdown('<div class="toast">✅ Listing generated successfully!</div>', unsafe_allow_html=True)
                    st.markdown(f"### 📋 Your AI-Optimised Listing\n\n{listing}")
                    st.download_button("⬇ Download Listing", listing, file_name="listing.txt")

                except Exception as e:
                    st.error(f"⚠️ Error: {e}")
        else:
            st.warning("⚠️ Your trial has ended. Please upgrade to continue.")
            if st.button("💳 Upgrade Now"):
                checkout_url = create_checkout_session(user_email)
                st.markdown(f"[👉 Click here to upgrade your plan]({checkout_url})", unsafe_allow_html=True)

# ----------------------
# BILLING PAGE
# ----------------------
elif page == "💳 Billing":
    st.markdown("## 💳 Billing & Subscription")
    email = st.text_input("Enter your email to manage your plan:")
    if email and st.button("Manage Subscription"):
        checkout_url = create_checkout_session(email)
        st.markdown(f"[👉 Open Billing Portal]({checkout_url})", unsafe_allow_html=True)
    else:
        st.info("Enter your dealership email to view or upgrade your plan.")

# ----------------------
# SUPPORT PAGE
# ----------------------
elif page == "📞 Support":
    st.markdown("## 📞 Support & Contact")
    st.markdown("""
If you need help or have questions, contact our support team:
- 📧 [support@dealercommand.ai](mailto:support@dealercommand.ai)
- 🌐 Visit [www.carfundo.com](https://www.carfundo.com)
    """)

# ----------------------
# FOOTER
# ----------------------
st.markdown('<div class="footer">© 2025 DealerCommand AI — Powered by Carfundo</div>', unsafe_allow_html=True)
