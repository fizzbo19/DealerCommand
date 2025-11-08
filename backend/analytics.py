# backend/analytics.py
import pandas as pd
from backend.sheet_utils import get_listing_history_df, get_social_media_data, filter_social_media

def top_platform_for_batch(make=None, model=None, min_price=None, max_price=None, fuel=None):
    """
    Returns top performing social media platform for a batch of cars.
    """
    sm_df = get_social_media_data()
    filtered = filter_social_media(sm_df, make, model, min_price, max_price, fuel)
    
    if filtered.empty:
        return "No data available for selected filters."
    
    grouped = filtered.groupby("Platform").agg({
        "Reach": "sum",
        "Impressions": "sum",
        "Revenue": "sum"
    }).reset_index()
    
    best_platform = grouped.sort_values("Revenue", ascending=False).iloc[0]
    return {
        "Platform": best_platform.Platform,
        "Total Reach": int(best_platform.Reach),
        "Total Impressions": int(best_platform.Impressions),
        "Estimated Revenue": int(best_platform.Revenue)
    }

def dealer_ai_recommendations(user_email):
    """
    Provides AI-like recommendations based on listing history.
    """
    df = get_listing_history_df()
    user_df = df[df["Email"].str.lower() == user_email.lower()]
    if user_df.empty:
        return "No historical listings yet to provide recommendations."
    
    recommendations = []
    
    most_common_make = user_df["Make"].mode()[0] if "Make" in user_df.columns else None
    if most_common_make:
        recommendations.append(f"🚗 Focus on your most listed make: {most_common_make}")
    
    avg_price = user_df["Price"].replace('£','', regex=True).astype(float).mean() if "Price" in user_df.columns else None
    if avg_price:
        recommendations.append(f"💰 Average price of your listings is £{int(avg_price)} — consider pricing strategies around this.")

    # Highlight high-performing car types
    if "Model" in user_df.columns:
        top_model = user_df["Model"].mode()[0]
        recommendations.append(f"🏎️ Your top performing model is {top_model} — consider promoting similar listings.")

    return recommendations

