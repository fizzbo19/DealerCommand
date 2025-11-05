# backend/stripe_utils.py
import os
import stripe

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

def create_checkout_session(price_id, customer_email, success_url=None, cancel_url=None):
    if not stripe.api_key:
        return None
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            customer_email=customer_email,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url or "https://your-site/success",
            cancel_url=cancel_url or "https://your-site/cancel",
        )
        return session.url
    except Exception:
        return None
