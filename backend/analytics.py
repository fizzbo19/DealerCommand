# backend/analytics.py

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ---------------------------------------------------------
# IMPORTS (backend deps)
# ---------------------------------------------------------
from backend.sheet_utils import (
    get_inventory_for_user,
    get_social_media_data,
    get_sheet_data
)


# ---------------------------------------------------------
# PRICE PARSING (global safe helper)
# ---------------------------------------------------------
def _parse_price(value):
    """
    Converts values like '£12,995', '12995', '12k', None into a float.
    Returns None for anything that cannot be parsed.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    val = str(value).lower().strip()

    # Remove symbols & commas
    val = val.replace("£", "").replace(",", "").replace(" ", "")
    if val.endswith("k"):
        try:
            return float(val[:-1]) * 1000
        except:
            return None

    try:
        return float(val)
    except:
        return None


# ---------------------------------------------------------
# CLEAN INVENTORY
# ---------------------------------------------------------
def clean_inventory(df):
    """Standardises inventory columns & price fields for analytics."""
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # Standard column names
    rename_map = {
        "price": "Price",
        "mileage": "Mileage",
        "title": "Title",
        "model": "Model",
        "make": "Make",
        "year": "Year"
    }

    df.rename(columns={c: rename_map.get(c.lower(), c) for c in df.columns}, inplace=True)

    # Parse price
    if "Price" in df.columns:
        df["ParsedPrice"] = df["Price"].apply(_parse_price)
    else:
        df["ParsedPrice"] = None

    # Parse Year safely
    if "Year" in df.columns:
        df["Year"] = pd.to_numeric(df["Year"], errors="coerce")

    # Parse Mileage safely
    if "Mileage" in df.columns:
        df["Mileage"] = pd.to_numeric(df["Mileage"], errors="coerce")

    return df


# ---------------------------------------------------------
# CLEAN SOCIAL MEDIA DATA
# ---------------------------------------------------------
def clean_social(df):
    """
    Cleans & standardises the social media sheet structure:

    Date, Platform, Views, Likes, Comments, Shares, Reach
    """
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # Fix date column
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    # Numeric metrics
    numeric_cols = ["Views", "Likes", "Comments", "Shares", "Reach"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Standard platform names
    if "Platform" in df.columns:
        df["Platform"] = df["Platform"].astype(str).str.title()

    return df


# ---------------------------------------------------------
# INVENTORY SUMMARY
# ---------------------------------------------------------
def inventory_summary(df):
    """Returns summary stats for inventory."""
    if df.empty:
        return {
            "total_listings": 0,
            "avg_price": 0,
            "avg_mileage": 0,
            "oldest_car": None,
            "newest_car": None
        }

    return {
        "total_listings": len(df),
        "avg_price": float(df["ParsedPrice"].mean()) if "ParsedPrice" in df else 0,
        "avg_mileage": float(df["Mileage"].mean()) if "Mileage" in df else 0,
        "oldest_car": int(df["Year"].min()) if "Year" in df else None,
        "newest_car": int(df["Year"].max()) if "Year" in df else None
    }


# ---------------------------------------------------------
# SOCIAL MEDIA SUMMARY
# ---------------------------------------------------------
def social_summary(df):
    """Provides engagement & performance insights."""
    if df.empty:
        return {
            "total_posts": 0,
            "total_views": 0,
            "total_likes": 0,
            "total_comments": 0,
            "total_shares": 0,
            "top_platform": None
        }

    totals = {
        "total_posts": len(df),
        "total_views": int(df["Views"].sum()),
        "total_likes": int(df["Likes"].sum()),
        "total_comments": int(df["Comments"].sum()),
        "total_shares": int(df["Shares"].sum())
    }

    # Top platform by views
    platform_views = df.groupby("Platform")["Views"].sum().sort_values(ascending=False)
    top_platform = platform_views.index[0] if len(platform_views) > 0 else None

    totals["top_platform"] = top_platform

    return totals


# ---------------------------------------------------------
# INSIGHTS GENERATOR (NO AI CALL, PURE RULES)
# ---------------------------------------------------------
def generate_insights(inv_df, soc_df):
    insights = []

    # --- Inventory insights ---
    if not inv_df.empty:
        if "ParsedPrice" in inv_df.columns:
            avg_price = inv_df["ParsedPrice"].mean()
            if avg_price and avg_price > 20000:
                insights.append("Your inventory skews toward higher-value vehicles — promote finance options.")
            elif avg_price < 8000:
                insights.append("Your stock is value-focused — highlight budget-friendly buying guides.")

        if "Year" in inv_df.columns:
            if inv_df["Year"].min() < 2010:
                insights.append("You have older vehicles — consider promoting extended warranty packages.")

    # --- Social insights ---
    if not soc_df.empty:
        if soc_df["Views"].sum() > 100000:
            insights.append("Strong video performance — double down on short-form content.")
        if soc_df["Likes"].sum() < 200:
            insights.append("Engagement is low — try using trending sounds & better hooks in videos.")

    return insights


# ---------------------------------------------------------
# MAIN ANALYTICS ENTRYPOINT (Option C)
# ---------------------------------------------------------
def analytics_dashboard(user_email):
    """
    Returns:
    summary = {
       "inventory": {...},
       "social": {...}
    }

    dataframes = {
       "inventory": cleaned inventory df,
       "social": cleaned social df
    }

    insights = [ ... ]
    """

    # ------------------ Load data ------------------
    raw_inv = get_inventory_for_user(user_email)
    raw_social = get_social_media_data(user_email)

    inv_df = clean_inventory(raw_inv)
    soc_df = clean_social(raw_social)

    # ------------------ Summaries ------------------
    summary = {
        "inventory": inventory_summary(inv_df),
        "social": social_summary(soc_df)
    }

    # ------------------ Insights ------------------
    insights = generate_insights(inv_df, soc_df)

    return summary, {"inventory": inv_df, "social": soc_df}, insights


# ---------------------------------------------------------
# DEMO DATA GENERATION (used in dev mode)
# ---------------------------------------------------------
def generate_demo_data():
    """Returns fake datasets to allow analytics to run even without Google Sheets."""
    dates = pd.date_range(datetime.today() - timedelta(days=14), periods=14)

    social_demo = pd.DataFrame({
        "Date": dates,
        "Platform": ["TikTok", "Instagram"] * 7,
        "Views": np.random.randint(1000, 10000, size=14),
        "Likes": np.random.randint(10, 500, size=14),
        "Comments": np.random.randint(0, 50, size=14),
        "Shares": np.random.randint(0, 30, size=14),
        "Reach": np.random.randint(1000, 20000, size=14)
    })

    inv_demo = pd.DataFrame({
        "Title": ["BMW 1 Series", "Audi A3", "Mercedes A-Class"],
        "Price": ["£12,995", "£15,250", "£17,500"],
        "Mileage": [45000, 38000, 22000],
        "Year": [2018, 2019, 2020]
    })

    return {"inventory": inv_demo, "social": social_demo}
