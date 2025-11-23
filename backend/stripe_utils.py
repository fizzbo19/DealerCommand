# backend/stripe_utils.py
import os
import json
import pandas as pd
import stripe
import uuid
inv_id = item_data.get("Inventory_ID") or str(uuid.uuid4())

# ------------------------------------------------------------
# STRIPE CONFIG
# ------------------------------------------------------------
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PREMIUM_PRICE_ID = os.environ.get("STRIPE_PREMIUM_PRICE_ID")
STRIPE_PRO_PRICE_ID = os.environ.get("STRIPE_PRO_PRICE_ID")
STRIPE_PLATINUM_PRICE_ID = os.environ.get("STRIPE_PLATINUM_PRICE_ID")

STRIPE_SUCCESS_URL = os.environ.get("STRIPE_SUCCESS_URL", "https://dealercommand.tech/success")
STRIPE_CANCEL_URL  = os.environ.get("STRIPE_CANCEL_URL",  "https://dealercommand.tech/cancel")

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
    """Creates a Stripe checkout session."""
    if not STRIPE_SECRET_KEY:
        return None

    price_id = PLAN_PRICE_IDS.get(plan.lower())
    if not price_id:
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
        print("Stripe error:", e)
        return None


def get_subscription_details(session_id):
    """Retrieve subscription details."""
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
        print("Subscription lookup failed:", e)
        return None


# ===================================================================
# INVENTORY STORAGE (CSV BACKED) — REQUIRED BY FRONTEND
# ===================================================================
INVENTORY_CSV = "/opt/render/project/src/backend/inventory_data.csv"

def _load_inventory_df():
    if not os.path.exists(INVENTORY_CSV):
        df = pd.DataFrame(columns=[
           
    "Email", "Inventory_ID", "Make", "Model", "Year", "Price", "Mileage",
    "Color", "Fuel", "Transmission", "Features", "Notes", "Generated_Listing", "Created", "Images"
]

        )
        df.to_csv(INVENTORY_CSV, index=False)
        return df

    return pd.read_csv(INVENTORY_CSV)

def _save_inventory_df(df):
    df.to_csv(INVENTORY_CSV, index=False)

# ------------------------------------------------------------
# REQUIRED BY app.py
# ------------------------------------------------------------
def api_get_inventory(user_email):
    df = _load_inventory_df()
    user_rows = df[df["Email"].astype(str).str.lower() == user_email.lower()]
    return user_rows.to_dict(orient="records")

def api_save_inventory(user_email, item_data):
    df = _load_inventory_df()
    inv_id = item_data.get("Inventory_ID")

    # Create new ID if needed
    if not inv_id or pd.isna(inv_id):
        inv_id = f"car_{len(df) + 1}"
        item_data["Inventory_ID"] = inv_id

    # Remove old record
    df = df[df["Inventory_ID"] != inv_id]

    # Add new / updated record
    item_data["Email"] = user_email
    df = pd.concat([df, pd.DataFrame([item_data])], ignore_index=True)

    _save_inventory_df(df)
    return {"status": "saved", "Inventory_ID": inv_id}

def api_delete_inventory(user_email, inventory_id):
    df = _load_inventory_df()

    df = df[~(
        (df["Email"].astype(str).str.lower() == user_email.lower()) &
        (df["Inventory_ID"] == inventory_id)
    )]

    _save_inventory_df(df)
    return {"status": "deleted", "Inventory_ID": inventory_id}
