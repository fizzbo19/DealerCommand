import streamlit as st
from backend.sheet_utils import save_inventory_item, get_inventory_for_user, update_inventory_item, delete_inventory_item
import pandas as pd
from datetime import datetime
import uuid

st.set_page_config(page_title="Inventory | DealerCommand", layout="wide")

email = st.session_state.get("user_email")
if not email:
    st.warning("Please login first.")
    st.stop()

st.title("📦 Inventory Management")

# --- Add / New Listing ---
with st.expander("➕ Add New Car"):
    cols = st.columns(2)
    with cols[0]:
        make = st.text_input("Make")
        model = st.text_input("Model")
        year = st.text_input("Year")
        mileage = st.text_input("Mileage")
        color = st.text_input("Color")
    with cols[1]:
        fuel = st.selectbox("Fuel Type", ["Petrol", "Diesel", "Hybrid", "Electric"])
        transmission = st.selectbox("Transmission", ["Automatic", "Manual"])
        price = st.text_input("Price")
        features = st.text_area("Key Features")
        notes = st.text_area("Dealer Notes")

    if st.button("Save Car Listing"):
        item_id = str(uuid.uuid4())[:8]
        save_inventory_item(email, {
            "ID": item_id,
            "Make": make,
            "Model": model,
            "Year": year,
            "Mileage": mileage,
            "Color": color,
            "Fuel": fuel,
            "Transmission": transmission,
            "Price": price,
            "Features": features,
            "Notes": notes,
            "Status": "Active"
        })
        st.success(f"Car saved with ID: {item_id}")
        st.experimental_rerun()

# --- View / Manage Inventory ---
df = get_inventory_for_user(email)
if df.empty:
    st.info("No inventory found yet.")
else:
    for idx, row in df.iterrows():
        with st.expander(f"{row['Make']} {row['Model']} ({row['Year']}) - {row['Status']}"):
            st.write(row)
            if st.button(f"Delete {row['ID']}"):
                delete_inventory_item(row["ID"])
                st.success("Deleted successfully.")
                st.experimental_rerun()
# In Inventory tab
st.markdown("### 📈 Your Inventory")
df_inventory = get_sheet_data("Inventory")
user_inventory = df_inventory[df_inventory["Email"].str.lower() == user_email.lower()]

# Display image previews
if not user_inventory.empty and "Image_Link" in user_inventory.columns:
    for idx, row in user_inventory.iterrows():
        st.markdown(f"**{row['Year']} {row['Make']} {row['Model']}**")
        if row.get("Image_Link"):
            st.image(row["Image_Link"], width=300)
        st.write(row[["Mileage","Color","Fuel","Transmission","Price","Features","Notes","Listing"]])
        st.markdown("---")
else:
    st.dataframe(user_inventory)
