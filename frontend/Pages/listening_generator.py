# frontend/pages/3_Listing_Generator.py
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
from backend.ai_generator import generate_listing
from backend.trial_manager import maybe_increment_usage
from backend.trial_manager import get_trial_status

st.set_page_config(page_title="Listing Generator", layout="wide")

if not st.session_state.get("authenticated"):
    st.warning("Please login first.")
    st.stop()

email = st.session_state.get("user_email")
status, expiry, used = get_trial_status(email)

st.title("🧠 Listing Generator")

with st.form("create_listing"):
    make = st.text_input("Make", "BMW")
    model = st.text_input("Model", "X5 M Sport")
    year = st.text_input("Year", "2021")
    mileage = st.text_input("Mileage", "28,000 miles")
    color = st.text_input("Colour", "Black")
    fuel = st.selectbox("Fuel Type", ["Petrol", "Diesel", "Hybrid", "Electric"])
    transmission = st.selectbox("Transmission", ["Automatic", "Manual"])
    price = st.text_input("Price", "£45,995")
    tone = st.selectbox("Tone", ["Professional", "Sporty", "Luxury", "Casual"])
    features = st.text_area("Key features", "Panoramic roof, heated seats")
    notes = st.text_area("Dealer notes (optional)", "Full service history, finance available")
    submitted = st.form_submit_button("Generate Listing")

if submitted:
    prompt_data = {
        "make": make, "model": model, "year": year, "mileage": mileage,
        "color": color, "fuel": fuel, "transmission": transmission,
        "price": price, "features": features, "notes": notes, "tone": tone
    }
    try:
        listing_text = generate_listing(prompt_data)
        st.subheader("📋 Generated Listing")
        st.markdown(listing_text)
        st.download_button("⬇ Download listing", listing_text, file_name="car_listing.txt")
        # save usage (will only increment if trial allows)
        maybe_increment_usage(email, listing_text)
        st.success("Saved to your account (if your sheet is configured).")
    except Exception as e:
        st.error(f"AI or backend error: {e}")
