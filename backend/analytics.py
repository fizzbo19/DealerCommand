# backend/analytics.py
import pandas as pd
import numpy as np
from backend.sheet_utils import get_sheet_data
import matplotlib.pyplot as plt
import seaborn as sns
from io import BytesIO
from backend.sheet_utils import get_listing_history_df, get_social_media_data, filter_social_media

sns.set_style("whitegrid")

# -------------------------------
# UTILITY FUNCTIONS
# -------------------------------

def generate_chart_image(fig):
    """Convert matplotlib figure to PNG image bytes."""
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf

def convert_price_series(df, col="Price"):
    """Convert Price column from £ string to float."""
    if col in df.columns:
        return df[col].replace('£','', regex=True).astype(float)
    return pd.Series(dtype=float)

# -------------------------------
# PRO ANALYTICS
# -------------------------------

def pro_analytics(user_email):
    """
    Provides basic analytics (3 charts) for Pro plan users.
    """
    df = get_listing_history_df()
    user_df = df[df["Email"].str.lower() == user_email.lower()]
    if user_df.empty:
        return {"error": "No historical listings to analyze."}

    analytics = {}

    # 1️⃣ Listings per Make
    make_counts = user_df["Make"].value_counts()
    fig1, ax1 = plt.subplots()
    make_counts.plot(kind='bar', ax=ax1, color='skyblue')
    ax1.set_title("Number of Listings per Make")
    ax1.set_ylabel("Listings")
    analytics['chart_listings_per_make'] = generate_chart_image(fig1)

    # 2️⃣ Average Price per Make
    avg_price_make = user_df.groupby("Make")["Price"].replace('£','',regex=True).astype(float).mean()
    fig2, ax2 = plt.subplots()
    avg_price_make.plot(kind='bar', ax=ax2, color='orange')
    ax2.set_title("Average Price per Make")
    ax2.set_ylabel("Price (£)")
    analytics['chart_avg_price_per_make'] = generate_chart_image(fig2)

    # 3️⃣ Top Models by Count
    top_models = user_df["Model"].value_counts().head(5)
    fig3, ax3 = plt.subplots()
    top_models.plot(kind='bar', ax=ax3, color='green')
    ax3.set_title("Top 5 Models by Listings")
    ax3.set_ylabel("Listings")
    analytics['chart_top_models'] = generate_chart_image(fig3)

    # Simple recommendations
    most_common_make = user_df["Make"].mode()[0]
    top_model = user_df["Model"].mode()[0]
    avg_price = convert_price_series(user_df).mean()
    analytics['recommendations'] = [
        f"🚗 Focus on your most listed make: {most_common_make}",
        f"🏎️ Promote your top performing model: {top_model}",
        f"💰 Average listing price is £{int(avg_price)} — consider optimizing pricing."
    ]

    return analytics

# -------------------------------
# PLATINUM ANALYTICS
# -------------------------------

def platinum_analytics(user_email):
    """
    Provides detailed analytics (5+ charts and recommendations) for Platinum plan users.
    """
    df = get_listing_history_df()
    user_df = df[df["Email"].str.lower() == user_email.lower()]
    if user_df.empty:
        return {"error": "No historical listings to analyze."}

    analytics = {}

    # Convert price
    prices = convert_price_series(user_df)

    # 1️⃣ Revenue over Time
    user_df['Timestamp'] = pd.to_datetime(user_df['Timestamp'])
    revenue_over_time = user_df.groupby(user_df['Timestamp'].dt.to_period('M'))['Price'].replace('£','', regex=True).astype(float).sum()
    fig1, ax1 = plt.subplots(figsize=(8,4))
    revenue_over_time.plot(ax=ax1, marker='o', color='purple')
    ax1.set_title("Revenue Over Time")
    ax1.set_ylabel("Revenue (£)")
    analytics['chart_revenue_over_time'] = generate_chart_image(fig1)

    # 2️⃣ Platform Performance
    sm_df = get_social_media_data()
    platform_df = filter_social_media(sm_df, None, None, None, None, None)
    platform_summary = platform_df.groupby('Platform').agg({'Revenue':'sum', 'Reach':'sum', 'Impressions':'sum'}).reset_index()
    fig2, ax2 = plt.subplots(figsize=(8,4))
    platform_summary.plot(x='Platform', y='Revenue', kind='bar', ax=ax2, color='teal')
    ax2.set_title("Revenue by Platform")
    ax2.set_ylabel("Revenue (£)")
    analytics['chart_platform_performance'] = generate_chart_image(fig2)

    # 3️⃣ Listings per Make
    make_counts = user_df["Make"].value_counts()
    fig3, ax3 = plt.subplots(figsize=(6,4))
    make_counts.plot(kind='bar', ax=ax3, color='skyblue')
    ax3.set_title("Listings per Make")
    analytics['chart_listings_per_make'] = generate_chart_image(fig3)

    # 4️⃣ Top Models by Revenue
    model_revenue = user_df.groupby("Model")["Price"].replace('£','', regex=True).astype(float).sum().sort_values(ascending=False).head(5)
    fig4, ax4 = plt.subplots(figsize=(6,4))
    model_revenue.plot(kind='bar', ax=ax4, color='orange')
    ax4.set_title("Top 5 Models by Revenue")
    analytics['chart_top_models_revenue'] = generate_chart_image(fig4)

    # 5️⃣ Average Price per Make
    avg_price_make = user_df.groupby("Make")["Price"].replace('£','', regex=True).astype(float).mean()
    fig5, ax5 = plt.subplots(figsize=(6,4))
    avg_price_make.plot(kind='bar', ax=ax5, color='green')
    ax5.set_title("Average Price per Make")
    ax5.set_ylabel("Price (£)")
    analytics['chart_avg_price_per_make'] = generate_chart_image(fig5)

    # Optional: Top 5 listings by revenue
    top_listings = user_df.copy()
    top_listings['Price'] = convert_price_series(top_listings)
    top_listings = top_listings.sort_values('Price', ascending=False).head(5)
    analytics['top_listings'] = top_listings[["Make","Model","Year","Price","Mileage"]]

    # Advanced Recommendations
    most_common_make = user_df["Make"].mode()[0]
    top_model = user_df["Model"].mode()[0]
    avg_price = prices.mean()
    analytics['recommendations'] = [
        f"🚗 Focus on your most listed make: {most_common_make}",
        f"🏎️ Promote your top performing model: {top_model}",
        f"💰 Average listing price is £{int(avg_price)} — consider adjusting pricing.",
        "📈 Allocate more posts to platforms with highest revenue (see chart).",
        "🔎 Consider sourcing more vehicles similar to top performing models.",
        "⚡ Optimize your pricing strategy based on top revenue listings."
    ]

    return analytics



# ----------------------
# Fetch user listing and social media data
# ----------------------
# backend/analytics_backend.py


# ----------------------
# Fetch user analytics data
# ----------------------
# backend/analytics.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from backend.sheet_utils import get_inventory_for_user

def get_user_analytics_data(user_email):
    """
    Returns analytics data for the user.
    If no real listings exist, returns demo data automatically.
    """
    # Fetch user listings
    df = get_inventory_for_user(user_email)
    
    # If user has no data, create demo DataFrame
    if df.empty:
        np.random.seed(42)
        demo_dates = pd.date_range(end=datetime.today(), periods=12, freq="M")
        df = pd.DataFrame({
            "Date": demo_dates,
            "Revenue": np.random.randint(2000, 10000, size=12),
            "Reach": np.random.randint(5000, 20000, size=12),
            "Impressions": np.random.randint(10000, 40000, size=12),
            "Make": np.random.choice(["BMW", "Audi", "Mercedes", "Toyota"], size=12),
            "Model": np.random.choice(["X5","A3","C-Class","Corolla"], size=12),
            "Platform": np.random.choice(["Facebook","Instagram","TikTok"], size=12),
            "Price": np.random.randint(20000, 50000, size=12)
        })
        df["Demo"] = True
    else:
        df["Demo"] = False
        # Ensure required columns exist for plotting
        for col in ["Revenue", "Reach", "Impressions", "Platform", "Price"]:
            if col not in df.columns:
                df[col] = 0

        # Ensure Date is datetime
        if "Date" not in df.columns:
            df["Date"] = pd.to_datetime(df["Timestamp"])
        else:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    
    return df

def platinum_recommendations(filtered_df):
    """
    Generates AI-like suggestions based on filtered analytics data.
    """
    recs = []

    # Top performing platform
    if "Platform" in filtered_df.columns:
        platform_rev = filtered_df.groupby("Platform")["Revenue"].sum().sort_values(ascending=False)
        if not platform_rev.empty:
            top_platform = platform_rev.index[0]
            recs.append(f"🚀 Focus on your top platform: {top_platform}")

    # Price recommendations
    if "Price" in filtered_df.columns and not filtered_df["Price"].empty:
        avg_price = int(filtered_df["Price"].mean())
        recs.append(f"💰 Average listing price is £{avg_price} — consider pricing strategies around this.")

    # Top model recommendations
    if "Model" in filtered_df.columns:
        top_model = filtered_df.groupby("Model")["Revenue"].sum().sort_values(ascending=False).index[0]
        recs.append(f"🏎️ Your top-performing model is {top_model} — consider promoting similar listings.")

    # Posting frequency recommendation
    if "Date" in filtered_df.columns:
        freq = round(filtered_df.groupby(filtered_df["Date"].dt.date).size().mean(), 1)
        recs.append(f"📅 Average posting frequency is {freq} posts/day — try maintaining consistent posting.")

    return recs


# ----------------------
# Platinum AI Recommendations
# ----------------------
def platinum_recommendations(df):
    """
    Generates advanced Platinum-level actionable recommendations.
    """
    recommendations = []
    if df.empty:
        return ["No data available to generate recommendations."]

    # Top Make / Model by Revenue
    if "Make" in df.columns and "Revenue" in df.columns:
        top_make = df.groupby("Make")["Revenue"].sum().idxmax()
        recommendations.append(f"🚗 Focus more on your top-performing make: {top_make}")

    if "Model" in df.columns and "Revenue" in df.columns:
        top_model = df.groupby("Model")["Revenue"].sum().idxmax()
        recommendations.append(f"🏎️ Promote your highest revenue model: {top_model}")

    # Pricing insights
    if "Price" in df.columns and "Revenue" in df.columns:
        avg_price = df["Price"].mean()
        avg_rev = df["Revenue"].mean()
        if avg_rev < avg_price * 0.8:
            recommendations.append("💰 Consider revising prices to increase conversion rates.")

    # Best Platform
    if "Platform" in df.columns:
        best_platform = df.groupby("Platform")["Revenue"].sum().idxmax()
        recommendations.append(f"🌐 Focus on promoting listings on {best_platform} — highest revenue platform.")

    # Posting frequency & engagement
    if "Date" in df.columns:
        recent_30 = df[df["Date"] >= pd.Timestamp.today() - pd.Timedelta(days=30)]
        if len(recent_30) < 5:
            recommendations.append("📅 Increase posting frequency to at least 5 listings/month for better engagement.")

        # Seasonality insight
        if not df["Date"].empty:
            df["Weekday"] = df["Date"].dt.day_name()
            top_day = df.groupby("Weekday")["Revenue"].sum().idxmax()
            recommendations.append(f"📈 Your listings perform best on {top_day}s — schedule posts accordingly.")

    return recommendations

# ----------------------
# Trend Analysis for Charts
# ----------------------
def get_trend_data(df, column="Revenue", freq="W"):
    """
    Returns aggregated trend data over time.
    freq: 'D'=day, 'W'=week, 'M'=month
    """
    if df.empty or column not in df.columns:
        return pd.DataFrame()
    trend = df.resample(freq, on="Date")[column].sum().reset_index()
    return trend

# ----------------------
# Top N Listings
# ----------------------
def top_listings(df, n=5, by="Revenue"):
    """
    Returns top N listings sorted by Revenue, Reach, or Impressions
    """
    if df.empty or by not in df.columns:
        return pd.DataFrame()
    return df.sort_values(by, ascending=False).head(n)

# ----------------------
# Platform Comparison
# ----------------------
def platform_summary(df):
    """
    Summarizes revenue, reach, impressions by platform.
    """
    if df.empty or "Platform" not in df.columns:
        return pd.DataFrame()
    summary = df.groupby("Platform")[["Revenue","Reach","Impressions"]].sum().reset_index()
    summary = summary.sort_values("Revenue", ascending=False)
    return summary

# ----------------------
# Advanced Insights
# ----------------------
def platinum_insights(df):
    """
    Returns structured insights for Platinum users for dashboard display.
    """
    insights = {}
    insights["Top Makes"] = df.groupby("Make")["Revenue"].sum().sort_values(ascending=False).head(3).to_dict() if "Make" in df.columns else {}
    insights["Top Models"] = df.groupby("Model")["Revenue"].sum().sort_values(ascending=False).head(3).to_dict() if "Model" in df.columns else {}
    insights["Average Price"] = round(df["Price"].mean(), 2) if "Price" in df.columns else 0
    insights["Average Revenue"] = round(df["Revenue"].mean(), 2) if "Revenue" in df.columns else 0
    insights["Best Platform"] = df.groupby("Platform")["Revenue"].sum().idxmax() if "Platform" in df.columns else None
    insights["Posting Frequency"] = df["Date"].dt.date.value_counts().mean() if "Date" in df.columns else 0
    return insights
