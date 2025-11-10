# backend/stripe_utils.py
import os
import stripe

# --------------------------
# ENVIRONMENT VARIABLES
# --------------------------
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PREMIUM_PRICE_ID = os.environ.get("STRIPE_PREMIUM_PRICE_ID")  # £29.99/month
STRIPE_PRO_PRICE_ID = os.environ.get("STRIPE_PRO_PRICE_ID")          # £59.99/month
STRIPE_SUCCESS_URL = os.environ.get("STRIPE_SUCCESS_URL", "https://dealercommand.tech/success")
STRIPE_CANCEL_URL = os.environ.get("STRIPE_CANCEL_URL", "https://dealercommand.tech/cancel")

stripe.api_key = STRIPE_SECRET_KEY


# --------------------------
# CREATE CHECKOUT SESSION
# --------------------------
def create_checkout_session(user_email, plan="premium"):
    """
    Create a Stripe Checkout session for a user based on selected plan.
    Supported plans: 'premium', 'pro'
    """

    if not STRIPE_SECRET_KEY:
        print("❌ Missing STRIPE_SECRET_KEY in environment.")
        return None

    # Select the appropriate Price ID
    price_id = None
    if plan == "pro":
        price_id = STRIPE_PRO_PRICE_ID
    elif plan == "premium":
        price_id = STRIPE_PREMIUM_PRICE_ID

    if not price_id:
        print(f"⚠️ Missing Price ID for plan: {plan}. Please check environment variables.")
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
    Returns plan type, customer email, and status if available.
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

