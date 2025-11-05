# frontend/app.py
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
from pathlib import Path

st.set_page_config(page_title="DealerCommand AI", page_icon="🚗", layout="wide")

# session state defaults
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "user_email" not in st.session_state:
    st.session_state["user_email"] = ""

# Logo detection (robust)
logo_paths = [
    Path(__file__).parent / "assets" / "dealercommand_logo.png",
    Path(__file__).parent / "Assets" / "dealercommand_logo.png"
]
logo_path = next((p for p in logo_paths if p.exists()), None)

st.markdown("<div style='display:flex;align-items:center;gap:16px'>", unsafe_allow_html=True)
if logo_path:
    st.image(str(logo_path), width=80)
else:
    st.markdown("### DealerCommand")
st.markdown("<div style='flex:1'></div>", unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

st.title("DealerCommand — AI for dealerships")
st.markdown("Navigate using the left sidebar pages — Login, Dashboard, Listing Generator, Captions, Pricing.")

# Keep UI minimal here — Streamlit will use pages/ to show subpages
if not st.session_state["authenticated"]:
    st.info("If you already have an account go to the **Login** page. New users can sign up there too.")
else:
    st.success(f"Signed in as: {st.session_state['user_email']}")

st.markdown("---")
st.caption("If you'd like a single-page app instead of multiple pages, tell me and I will combine them.")

