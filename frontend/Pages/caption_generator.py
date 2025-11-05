# frontend/pages/4_Caption_Generator.py
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
from backend.ai_generator import generate_caption

st.set_page_config(page_title="Caption Generator", layout="centered")

if not st.session_state.get("authenticated"):
    st.warning("Please login first.")
    st.stop()

st.title("🎥 Caption Generator")
make = st.text_input("Car make (for caption)")
model = st.text_input("Car model")
desc = st.text_area("Short prompt (e.g. highlight, features, vibe)")

if st.button("Generate Caption"):
    if not desc:
        st.warning("Enter a short prompt.")
    else:
        try:
            caption = generate_caption({"make": make, "model": model, "desc": desc})
            st.markdown("**Suggested caption:**")
            st.write(caption)
            st.download_button("⬇ Download caption", caption, file_name="caption.txt")
        except Exception as e:
            st.error(f"Caption generation failed: {e}")
