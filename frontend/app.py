import sys
import os
from datetime import datetime

import streamlit as st
from openai import OpenAI

# Backend path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Backend Imports
from backend.trial_manager import ensure_user_and_get_status, increment_usage
from backend.sheet_utils import append_to_google_sheet
from backend.stripe_utils import create_checkout_session


# ----------------------
# Streamlit UI Config
# ----------------------
st.set_page_config(page_title="🚗 DealerCommand AI", layout="centered")
st.title("🚗 DealerCommand AI - Premium Trial")

st.markdown("""
Welcome to **DealerCommand** — your AI-powered assistant for creating professional, high-converting car listings.  
Enjoy a **3-month premium trial** with full access to all tools before choosing a plan.
""")

# ----------------------
# User Inputs
# ----------------------
user_email = st.text_input("Enter your dealership email to start your trial", "")
api_key = st.text_input("Enter your OpenAI API key", type="password")

if user_email:
    # Get trial info
    status, expiry, usage_count = ensure_user_and_get_status(user_email)
    is_active = status in ["active", "new"]

    if is_active:
        st.success(f"🎉 Your 3-month premium trial is active! Trial ends: **{expiry}** — Listings used: **{usage_count}**")
    else:
        st.warning("⚠️ Your trial has ended. Please upgrade to continue.")
        if st.button("💳 Upgrade Now"):
            try:
                checkout_url = create_checkout_session(user_email)
                st.markdown(f"[👉 Click here to upgrade your plan]({checkout_url})")
            except Exception as e:
                st.error(f"Payment error: {e}")

    # ----------------------
    # Listing Generation Form
    # ----------------------
    if is_active:
        with st.form("car_form"):
            st.subheader("🧾 Generate Car Listing")
            make = st.text_input("Car Make", "BMW")
            model = st.text_input("Model", "X5 M Sport")
            year = st.text_input("Year", "2021")
            mileage = st.text_input("Mileage", "28,000 miles")
            color = st.text_input("Color", "Black")
            fuel = st.selectbox("Fuel Type", ["Petrol", "Diesel", "Hybrid", "Electric"])
            transmission = st.selectbox("Transmission", ["Automatic", "Manual"])
            price = st.text_input("Price", "£45,995")
            features = st.text_area("Key Features", "Panoramic roof, heated seats, M Sport package")
            notes = st.text_area("Dealer Notes (optional)", "Full service history, finance available")
            submit = st.form_submit_button("✨ Generate Listing")

        if submit:
            if not api_key:
                st.warning("⚠️ Please enter your OpenAI API key.")
            else:
                try:
                    client = OpenAI(api_key=api_key)

                    # AI Prompt
                    prompt = f"""
You are an expert automotive marketing assistant. 
Write a professional, engaging listing for this car:

Make: {make}
Model: {model}
Year: {year}
Mileage: {mileage}
Color: {color}
Fuel Type: {fuel}
Transmission: {transmission}
Price: {price}
Features: {features}
Dealer Notes: {notes}

Guidelines:
- 100–150 words
- Highlight top 3 selling points
- Friendly yet persuasive tone
- Include relevant emojis
"""

                    with st.spinner("🤖 Generating your listing..."):
                        response = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {"role": "system", "content": "You are a car sales assistant that writes engaging listings."},
                                {"role": "user", "content": prompt},
                            ],
                            temperature=0.7,
                        )
                        listing = response.choices[0].message.content.strip()

                    # Display AI result
                    st.subheader("📋 Generated Listing:")
                    st.markdown(listing)
                    st.download_button("⬇️ Download Listing", listing, file_name="car_listing.txt")

                    # Save to Google Sheets
                    car_data = {
                        "Make": make,
                        "Model": model,
                        "Year": year,
                        "Mileage": mileage,
                        "Color": color,
                        "Fuel Type": fuel,
                        "Transmission": transmission,
                        "Price": price,
                        "Features": features,
                        "Dealer Notes": notes,
                    }
                    append_to_google_sheet(user_email, car_data)
                    increment_usage(user_email, listing)

                    st.success("✅ Listing generated and saved successfully!")

                except Exception as e:
                    st.error(f"⚠️ Error generating listing: {e}")
else:
    st.info("👋 Enter your dealership email above to begin your 3-month premium trial.")
