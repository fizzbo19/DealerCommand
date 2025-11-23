import os
import json
import pandas as pd
import stripe
import uuid

# ------------------------------------------------------------
# STRIPE CONFIG
# ------------------------------------------------------------
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PREMIUM_PRICE_ID = os.environ.get("STRIPE_PREMIUM_PRICE_ID")
STRIPE_PRO_PRICE_ID = os.environ.get("STRIPE_PRO_PRICE_ID")
STRIPE_PLATINUM_PRICE_ID = os.environ.get("STRIPE_PLATINUM_PRICE_ID")

STRIPE_SUCCESS_URL = os.environ.get("STRIPE_SUCCESS_URL", "https://dealercommand.tech/success")
STRIPE_CANCEL_URL  = os.environ.get("STRIPE_CANCEL_URL",  "https://dealercommand.tech/cancel")

# Initialize Stripe API key only if it exists
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

PLAN_PRICE_IDS = {
    "premium": STRIPE_PREMIUM_PRICE_ID,
    "pro": STRIPE_PRO_PRICE_ID,
    "platinum": STRIPE_PLATINUM_PRICE_ID
}

# ------------------------------------------------------------
# STRIPE CHECKOUT SESSION
# ------------------------------------------------------------
def create_checkout_session(user_email, plan="premium"):
    """Creates a Stripe checkout session for subscription upgrade."""
    if not STRIPE_SECRET_KEY:
        print("⚠️ Stripe secret key missing. Cannot create checkout session.")
        return None

    price_id = PLAN_PRICE_IDS.get(plan.lower())
    if not price_id:
        print(f"⚠️ Price ID not found for plan: {plan}")
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
            allow_promotion_codes=True,
            # Pass user info or plan for fulfillment logic after successful checkout
            metadata={
                "user_email": user_email,
                "plan_upgrade": plan
            }
        )
        return session.url

    except Exception as e:
        print("Stripe error during session creation:", e)
        return None


def get_subscription_details(session_id):
    """Retrieve subscription details after a successful checkout."""
    if not STRIPE_SECRET_KEY:
        return None
        
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        subscription = stripe.Subscription.retrieve(session.subscription)
        customer = stripe.Customer.retrieve(session.customer)

        return {
            "customer_email": customer.email,
            "plan_id": subscription.items.data[0].price.id,
            "status": subscription.status,
            "metadata": session.metadata # Access the custom data we stored
        }

    except Exception as e:
        print("Subscription lookup failed:", e)
        return None

# The inventory storage logic (CSV-backed functions) has been removed, 
# as inventory persistence is handled exclusively by backend/sheet_utils.py.