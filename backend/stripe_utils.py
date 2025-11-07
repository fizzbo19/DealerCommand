# backend/stripe_utils.py
import os
import stripe

# Read Stripe keys from environment variables
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_SUCCESS_URL = os.environ.get("STRIPE_SUCCESS_URL", "https://yourdomain.com/success")
STRIPE_CANCEL_URL = os.environ.get("STRIPE_CANCEL_URL", "https://yourdomain.com/cancel")

stripe.api_key = STRIPE_SECRET_KEY

def create_checkout_session(user_email, price_id=None):
    """
    Creates a Stripe Checkout session for the given user and price_id.
    Returns the session URL or None if failure.
    """
    if not STRIPE_SECRET_KEY:
        print("❌ STRIPE_SECRET_KEY not set in environment.")
        return None
    if not price_id:
        print("❌ price_id not provided.")
        return None

    try:
        session = stripe.checkout.Session.create(
            customer_email=user_email,
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=STRIPE_SUCCESS_URL,
            cancel_url=STRIPE_CANCEL_URL,
        )
        return session.url
    except Exception as e:
        print(f"⚠️ Stripe session creation failed: {e}")
        return None
