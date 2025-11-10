import streamlit as st
from datetime import datetime

st.set_page_config(page_title="DealerCommand - Subscription Activated", page_icon="✅")

# 🎉 Success Page
st.title("✅ Subscription Activated Successfully!")

st.markdown("""
### Thank you for upgrading to **DealerCommand**!
Your subscription is now active, and you have full access to all premium features.

Here’s a quick summary of your account:
""")

# Normally you'd fetch this data dynamically — for now we’ll show placeholders.
st.markdown("""
- **👤 Account Email:** _[Your Email Address]_  
- **💼 Plan:** _[Premium or Pro]_  
- **📅 Activation Date:** _{date}_
""".format(date=datetime.now().strftime("%B %d, %Y")))

st.divider()

st.markdown("""
### 🚀 Next Steps
- Head back to your dashboard to start exploring your upgraded tools.  
- Your new features are now fully unlocked, including AI listings, analytics, and automation.  
- You’ll also receive a confirmation email from Stripe with your payment receipt.
""")

st.success("You're all set to supercharge your dealership with DealerCommand!")

st.page_link("app.py", label="⬅️ Return to Dashboard", icon="🏠")

st.markdown("---")
st.markdown("💬 Need help? [Contact support](mailto:support@dealercommand.ai)")
