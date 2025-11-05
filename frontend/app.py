import sys
import os
import json
from datetime import datetime

import streamlit as st
from openai import OpenAI

# Add root directory to Python path so 'backend' imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Backend imports
from backend.trial_manager import check_trial_status
from backend.sheet_utils import append_to_google_sheet
from backend.stripe_utils import create_checkout_session

# ----------------------
# Streamlit UI Config
# ----------------------
st.set_page_config(page_title="🚗 DealerCommand AI", layout="centered")
st.title("🚗 DealerCommand AI - Premium Trial")

st.markdown(
    """
Welcome to **DealerCommand** — your AI-powered assistant for creating professional, high-converting car listings.  
Enjoy a **3-month premium trial** with full access to all tools before choosing a plan.
"""
)

# ----------------------
# User Inputs
# ----------------------
user_email = st.text_input("Enter your dealership email to start your trial", "")
api_key = st.text_input("Enter your OpenAI API key", type="password")

if user_email:
    # Check if user is in trial and get usage count
    in_trial, trial_start, usage_count = check_trial_status(user_email)

    if in_trial:
        st.success(f"🎉 You’re in your 3-month premium trial! Started: {trial_start.date()} — Listings used: {usage_count}")
    else:
        st.warning("⚠️ Your trial has ended. Please upgrade to continue generating listings.")
        if st.button("Upgrade Now"):
            checkout_url = create_checkout_session(user_email)
            st.markdown(f"[💳 Click here to upgrade]({checkout_url})")

    # ----------------------
    # Listing Generation Form
    # ----------------------
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
        submit = st.form_submit_button("Generate Listing")

    if submit:
        if not api_key:
            st.warning("⚠️ Please enter your OpenAI API key.")
        elif not in_trial:
            st.error("⚠️ Trial expired. Upgrade to continue.")
        else:
            try:
                # Initialize OpenAI client
                client = OpenAI(api_key=api_key)

                # Prompt for AI
                prompt = f"""
You are an expert car sales assistant. Create a compelling, detailed, and professional listing for a car with the following details:

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

The description should be 100–150 words, highlight the car’s main selling points, and include a friendly yet persuasive tone that builds urgency and trust.
Use separate paragraphs and include relevant emojis to make it engaging.
"""

                with st.spinner("Generating your listing..."):
                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": "You are a helpful car sales assistant."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.7,
                    )
                    listing = response.choices[0].message.content

                # Display listing
                st.subheader("📋 Generated Listing:")
                st.markdown(listing)
                st.download_button("⬇️ Download Listing", listing, file_name="car_listing.txt")

                # Save usage to Google Sheets
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
                st.success("✅ Car details saved to your dealership records!")

            except Exception as e:
                st.error(f"⚠️ Error: {e}")
else:
    st.info("👋 Enter your dealership email above to begin your 3-month premium trial.")
