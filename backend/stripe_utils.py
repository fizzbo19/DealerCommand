# backend/stripe_utils.py
import os
import stripe

# --------------------------
# ENVIRONMENT VARIABLES
# --------------------------
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PREMIUM_PRICE_ID = os.environ.get("STRIPE_PREMIUM_PRICE_ID")  # £29.99/month
STRIPE_PRO_PRICE_ID = os.environ.get("STRIPE_PRO_PRICE_ID")          # £59.99/month
STRIPE_PLATINUM_PRICE_ID = os.environ.get("STRIPE_PLATINUM_PRICE_ID")  # £119.99/month
STRIPE_SUCCESS_URL = os.environ.get("STRIPE_SUCCESS_URL", "https://dealercommand.tech/success")
STRIPE_CANCEL_URL = os.environ.get("STRIPE_CANCEL_URL", "https://dealercommand.tech/cancel")

stripe.api_key = STRIPE_SECRET_KEY

# Mapping plans to Price IDs
PLAN_PRICE_IDS = {
    "premium": STRIPE_PREMIUM_PRICE_ID,
    "pro": STRIPE_PRO_PRICE_ID
}

# --------------------------
# CREATE CHECKOUT SESSION
# --------------------------
def create_checkout_session(user_email, plan="premium"):
    """
    Create a Stripe Checkout session for a user based on selected plan.
    Supported plans: 'premium', 'pro'
    """
    if not STRIPE_SECRET_KEY:
        print("❌ STRIPE_SECRET_KEY not set in environment.")
        return None

    price_id = PLAN_PRICE_IDS.get(plan.lower())
    if not price_id:
        print(f"⚠️ Price ID for plan '{plan}' not found. Check environment variables.")
        return None

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            customer_email=user_email,
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=STRIPE_SUCCESS_URL,
            cancel_url=STRIPE_CANCEL_URL,
            billing_address_collection="auto",
            allow_promotion_codes=True
        )
        return session.url

    except Exception as e:
        print(f"⚠️ Stripe Checkout session creation failed: {e}")
        return None

# --------------------------
# RETRIEVE SUBSCRIPTION DETAILS
# --------------------------
def get_subscription_details(session_id):
    """
    Retrieves subscription details after checkout success.
    Returns customer email, plan_id, and subscription status.
    """
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        subscription = stripe.Subscription.retrieve(session.subscription)
        customer = stripe.Customer.retrieve(session.customer)

        return {
            "customer_email": customer.email,
            "plan_id": subscription.items.data[0].price.id,
            "status": subscription.status,
        }

    except Exception as e:
        print(f"⚠️ Failed to retrieve subscription details: {e}")
        return None
