# frontend/cancel.py
import streamlit as st

st.set_page_config(
    page_title="DealerCommand - Payment Cancelled",
    page_icon="⚠️",
    layout="centered"
)

st.markdown(
    """
    <div style="text-align:center; margin-top:5rem;">
        <h1 style="color:#ef4444;">⚠️ Payment Cancelled</h1>
        <p>Your subscription was not processed. You can retry or contact support for help.</p>

        <a href="/app" style="text-decoration:none;">
            <button style="padding:0.8rem 2rem; font-size:1rem; border:none; border-radius:8px; background:#2563eb; color:white; cursor:pointer;">
                Return to Dashboard
            </button>
        </a>
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown("---")
st.markdown("💬 Need help? [Contact support](mailto:support@dealercommand.ai)")
