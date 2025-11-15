# backend/analytics.py
import pandas as pd
import numpy as np
from io import BytesIO
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns
import os
from openai import OpenAI

from backend.sheet_utils import (
    get_sheet_data,
    get_listing_history_df,
    get_social_media_data,
    filter_social_media,
    get_inventory_for_user,
    get_inventory_for_cars
)

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
        return pd.to_numeric(df[col].replace('£','', regex=True), errors='coerce')
    return pd.Series(dtype=float)

def standardize_dates(df):
    """Ensure consistent Date column exists."""
    if "Date" not in df.columns:
        if "Timestamp" in df.columns:
            df["Date"] = pd.to_datetime(df["Timestamp"], errors="coerce")
        else:
            df["Date"] = pd.date_range(end=datetime.today(), periods=len(df))
    else:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df

def generate_demo_data():
    """Generates demo analytics data for new users or demo mode."""
    np.random.seed(42)
    demo_dates = pd.date_range(end=datetime.today(), periods=12, freq="M")
    return pd.DataFrame({
        "Date": demo_dates,
        "Revenue": np.random.randint(2000, 10000, size=12),
        "Reach": np.random.randint(5000, 20000, size=12),
        "Impressions": np.random.randint(10000, 40000, size=12),
        "Make": np.random.choice(["BMW", "Audi", "Mercedes", "Toyota"], size=12),
        "Model": np.random.choice(["X5","A3","C-Class","Corolla"], size=12),
        "Platform": np.random.choice(["Facebook","Instagram","TikTok"], size=12),
        "Price": np.random.randint(20000, 50000, size=12),
        "Fuel": np.random.choice(["Petrol", "Diesel", "Hybrid"], size=12),
        "Demo": True
    })

# -------------------------------
# CORE DASHBOARD HELPERS
# -------------------------------
def inventory_summary(email):
    df = get_inventory_for_user(email)
    if df.empty:
        return {"Total_Listings": 0, "Average_Price": 0, "Makes_Count": {}}
    total_listings = len(df)
    avg_price = pd.to_numeric(df["Price"], errors="coerce").mean()
    makes_count = df["Make"].value_counts().to_dict()
    return {"Total_Listings": total_listings, "Average_Price": round(avg_price, 2) if pd.notna(avg_price) else 0, "Makes_Count": makes_count}

def social_media_summary(email, platform=None):
    df = get_social_media_data(email)
    df = filter_social_media(df, platform)
    if df.empty:
        return {"Total_Views": 0, "Total_Likes": 0, "Total_Clicks": 0, "Revenue": 0}
    return {"Total_Views": int(df["Views"].sum()), "Total_Likes": int(df["Likes"].sum()), "Total_Clicks": int(df["Clicks"].sum()), "Revenue": round(df["Revenue"].sum(),2)}

def listing_trends(email, days=30):
    df = get_inventory_for_user(email)
    if df.empty or "Timestamp" not in df.columns:
        return {}
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    cutoff = datetime.utcnow() - timedelta(days=days)
    df_recent = df[df["Timestamp"] >= cutoff]
    return df_recent.groupby(df_recent["Timestamp"].dt.date).size().to_dict()

def top_listings(email, top_n=5):
    df = get_inventory_for_user(email)
    if df.empty:
        return []
    df["Price_numeric"] = pd.to_numeric(df["Price"], errors="coerce")
    top_df = df.sort_values("Price_numeric", ascending=False).head(top_n)
    return top_df[["Make","Model","Year","Price","Mileage","Fuel"]].to_dict(orient="records")

def compare_cars(email, car_ids):
    if not car_ids:
        return []
    df = get_inventory_for_cars(email, car_ids)
    if df.empty:
        return []
    return df.to_dict(orient="records")

# -------------------------------
# PRO ANALYTICS
# -------------------------------
def pro_analytics(user_email):
    df = get_listing_history_df()
    user_df = df[df["Email"].str.lower() == user_email.lower()]
    if user_df.empty:
        return {"error": "No historical listings to analyze."}

    analytics = {}
    user_df["Price"] = convert_price_series(user_df)
    user_df = standardize_dates(user_df)

    # Listings per Make
    make_counts = user_df["Make"].value_counts()
    fig1, ax1 = plt.subplots()
    make_counts.plot(kind='bar', ax=ax1, color='skyblue')
    ax1.set_title("Number of Listings per Make")
    ax1.set_ylabel("Listings")
    analytics['chart_listings_per_make'] = generate_chart_image(fig1)

    # Average Price per Make
    avg_price_make = user_df.groupby("Make")["Price"].mean()
    fig2, ax2 = plt.subplots()
    avg_price_make.plot(kind='bar', ax=ax2, color='orange')
    ax2.set_title("Average Price per Make")
    ax2.set_ylabel("Price (£)")
    analytics['chart_avg_price_per_make'] = generate_chart_image(fig2)

    # Top Models by Count
    top_models = user_df["Model"].value_counts().head(5)
    fig3, ax3 = plt.subplots()
    top_models.plot(kind='bar', ax=ax3, color='green')
    ax3.set_title("Top 5 Models by Listings")
    ax3.set_ylabel("Listings")
    analytics['chart_top_models'] = generate_chart_image(fig3)

    # Recommendations
    most_common_make = user_df["Make"].mode()[0]
    top_model = user_df["Model"].mode()[0]
    avg_price = user_df["Price"].mean()
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
    df = get_listing_history_df()
    user_df = df[df["Email"].str.lower() == user_email.lower()]
    if user_df.empty:
        return {"error": "No historical listings to analyze."}

    analytics = {}
    user_df["Price"] = convert_price_series(user_df)
    user_df = standardize_dates(user_df)

    # Revenue over Time
    revenue_over_time = user_df.groupby(user_df['Date'].dt.to_period('M'))['Price'].sum()
    fig1, ax1 = plt.subplots(figsize=(8,4))
    revenue_over_time.plot(ax=ax1, marker='o', color='purple')
    ax1.set_title("Revenue Over Time")
    ax1.set_ylabel("Revenue (£)")
    analytics['chart_revenue_over_time'] = generate_chart_image(fig1)

    # Platform Performance
    sm_df = get_social_media_data()
    platform_df = filter_social_media(sm_df, None)
    platform_summary = platform_df.groupby('Platform')[['Revenue','Reach','Impressions']].sum().reset_index()
    fig2, ax2 = plt.subplots(figsize=(8,4))
    platform_summary.plot(x='Platform', y='Revenue', kind='bar', ax=ax2, color='teal')
    ax2.set_title("Revenue by Platform")
    ax2.set_ylabel("Revenue (£)")
    analytics['chart_platform_performance'] = generate_chart_image(fig2)

    # Listings per Make
    make_counts = user_df["Make"].value_counts()
    fig3, ax3 = plt.subplots(figsize=(6,4))
    make_counts.plot(kind='bar', ax=ax3, color='skyblue')
    ax3.set_title("Listings per Make")
    analytics['chart_listings_per_make'] = generate_chart_image(fig3)

    # Top Models by Revenue
    model_revenue = user_df.groupby("Model")["Price"].sum().sort_values(ascending=False).head(5)
    fig4, ax4 = plt.subplots(figsize=(6,4))
    model_revenue.plot(kind='bar', ax=ax4, color='orange')
    ax4.set_title("Top 5 Models by Revenue")
    analytics['chart_top_models_revenue'] = generate_chart_image(fig4)

    # Average Price per Make
    avg_price_make = user_df.groupby("Make")["Price"].mean()
    fig5, ax5 = plt.subplots(figsize=(6,4))
    avg_price_make.plot(kind='bar', ax=ax5, color='green')
    ax5.set_title("Average Price per Make")
    ax5.set_ylabel("Price (£)")
    analytics['chart_avg_price_per_make'] = generate_chart_image(fig5)

    # Top Listings
    top_listings_df = user_df.sort_values("Price", ascending=False).head(5)
    analytics['top_listings'] = top_listings_df[["Make","Model","Year","Price","Mileage"]].to_dict(orient="records")

    # Recommendations
    analytics['recommendations'] = platinum_recommendations(user_df)
    return analytics

def platinum_recommendations(df):
    recs = []
    if df.empty:
        return ["No data available to generate recommendations."]
    if "Make" in df.columns and "Revenue" in df.columns:
        top_make = df.groupby("Make")["Revenue"].sum().idxmax()
        recs.append(f"🚗 Focus more on your top-performing make: {top_make}")
    if "Model" in df.columns and "Revenue" in df.columns:
        top_model = df.groupby("Model")["Revenue"].sum().idxmax()
        recs.append(f"🏎️ Promote your highest revenue model: {top_model}")
    if "Price" in df.columns:
        avg_price = df["Price"].mean()
        recs.append(f"💰 Average listing price is £{int(avg_price)} — optimize pricing.")
    if "Platform" in df.columns:
        best_platform = df.groupby("Platform")["Revenue"].sum().idxmax()
        recs.append(f"🌐 Promote listings on {best_platform}.")
    if "Date" in df.columns:
        recent_30 = df[df["Date"] >= pd.Timestamp.today() - pd.Timedelta(days=30)]
        if len(recent_30) < 5:
            recs.append("📅 Increase posting frequency to at least 5 listings/month.")
        df["Weekday"] = df["Date"].dt.day_name()
        top_day = df.groupby("Weekday")["Revenue"].sum().idxmax()
        recs.append(f"📈 Listings perform best on {top_day}s — schedule posts accordingly.")
    return recs

# -------------------------------
# FULL DASHBOARD
# -------------------------------
def analytics_dashboard(email, plan="Free", top_n=5, compare_ids=None):
    dashboard = {
        "Inventory": inventory_summary(email),
        "Social_Media": social_media_summary(email),
        "Top_Listings": top_listings(email, top_n),
        "Recommendations": generate_recommendations(email, plan)
    }
    if plan.lower() in ["pro", "platinum"]:
        dashboard["Listing_Trends"] = listing_trends(email)
    if compare_ids:
        dashboard["Compare_Cars"] = compare_cars(email, compare_ids)
    return dashboard

def generate_recommendations(email, plan="Free"):
    inv_summary = inventory_summary(email)
    sm_summary = social_media_summary(email)
    recs = []
    if plan.lower() == "free":
        if inv_summary["Total_Listings"] < 5:
            recs.append("Add more listings to reach potential buyers.")
        if sm_summary["Total_Views"] < 500:
            recs.append("Promote your cars on social media.")
    elif plan.lower() == "pro":
        recs.append("Consider pricing competitive cars slightly below market average.")
        if sm_summary["Revenue"] < 1000:
            recs.append("Boost posts on TikTok and Instagram for better reach.")
    elif plan.lower() == "platinum":
        recs.append("Focus on high-value listings for maximum revenue.")
        trends = listing_trends(email)
        if trends:
            trending_dates = sorted(trends.items(), key=lambda x: x[1], reverse=True)
            recs.append(f"Most active listing days recently: {trending_dates[:3]}")
        recs.append("Cross-promote top listings on YouTube, TikTok, and Instagram.")
    return recs

# -------------------------------
# STREAMLIT-FRIENDLY CHARTS
# -------------------------------
def render_charts_for_streamlit(user_email, plan="pro"):
    if plan.lower() == "platinum":
        analytics_data = platinum_analytics(user_email)
    elif plan.lower() == "pro":
        analytics_data = pro_analytics(user_email)
    else:
        return {"info": "Upgrade to Pro or Platinum to see analytics."}
    charts_dict = {}
    for key, value in analytics_data.items():
        charts_dict[key] = value
    return charts_dict

# -------------------------------
# Dealer Performance Score
# -------------------------------
def dealer_performance_score(user_email):
    inv_df = get_inventory_for_user(user_email)
    sm_df = filter_social_media(get_social_media_data(), None)
    total_listings = len(inv_df) if not inv_df.empty else 0
    total_revenue = pd.to_numeric(inv_df["Price"].replace('£','', regex=True), errors='coerce').sum() if not inv_df.empty else 0
    total_engagement = sm_df["Revenue"].sum() + sm_df["Reach"].sum() if not sm_df.empty else 0
    score = min(100, round((min(total_listings,50)/50)*40 + (min(total_revenue,500000)/500000)*40 + (min(total_engagement,100000)/100000)*20))
    return score

# -------------------------------
# Pro AI Recommendations
# -------------------------------
def pro_custom_recommendations(user_email):
    inv_df = get_inventory_for_user(user_email)
    sm_df = filter_social_media(get_social_media_data(), None)
    recs = []
    if inv_df.empty:
        recs.append("Add your first listings to get personalized recommendations.")
        return recs
    top_make = inv_df["Make"].mode()[0] if "Make" in inv_df.columns else None
    top_model = inv_df["Model"].mode()[0] if "Model" in inv_df.columns else None
    if top_make:
        recs.append(f"🚗 Focus on your top-selling make: {top_make}")
    if top_model:
        recs.append(f"🏎️ Promote your top-performing model: {top_model}")
    avg_price = pd.to_numeric(inv_df["Price"].replace('£','', regex=True), errors='coerce').mean() if "Price" in inv_df.columns else 0
    if avg_price > 0:
        recs.append(f"💰 Average listing price is £{int(avg_price)} — consider adjusting pricing strategies.")
    if not sm_df.empty:
        best_platform = sm_df.groupby("Platform")["Revenue"].sum().idxmax()
        recs.append(f"📈 Focus posts on {best_platform} for maximum revenue.")
    return recs

# -------------------------------
# Compare Cars Analytics
# -------------------------------
def compare_cars_analytics(user_email, car_ids):
    df = get_inventory_for_user(user_email)
    if df.empty or not car_ids:
        return pd.DataFrame()
    df = df[df.index.isin(car_ids)]
    compare_cols = ["Make","Model","Year","Mileage","Fuel","Price","Features","Revenue"]
    for col in compare_cols:
        if col not in df.columns:
            df[col] = "-"
    return df[compare_cols]

# -------------------------------
# CSV Export
# -------------------------------
def export_analytics_csv(df, filename="analytics_export.csv"):
    if df.empty:
        return None
    df.to_csv(filename, index=False)
    return filename

# -------------------------------
# AI Video Script Generator
# -------------------------------
def generate_ai_video_script(user_email, car_details):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "⚠️ OpenAI API key missing. Cannot generate video script."
    client = OpenAI(api_key=api_key)
    prompt = f"""
You are a professional automotive content creator. Create a 60–90 second engaging video script for a car listing:
{car_details.get('Year','')} {car_details.get('Make','')} {car_details.get('Model','')}, 
{car_details.get('Mileage','')} miles, {car_details.get('Color','')} color, {car_details.get('Fuel','')} fuel, 
{car_details.get('Transmission','')} transmission, priced at {car_details.get('Price','')}.
Features: {car_details.get('Features','')}. Dealer Notes: {car_details.get('Notes','')}.
Include: engaging language, emojis, and a call-to-action.
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content":"You are a top-tier automotive video content writer."},
                {"role":"user","content":prompt}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content.strip() if response and getattr(response, "choices", None) else ""
    except Exception as e:
        return f"⚠️ Failed to generate video script: {e}"

# -------------------------------
# Competitor Monitoring
# -------------------------------
def competitor_monitoring(user_email, competitor_csv=None, sheet_name=None):
    if competitor_csv:
        try:
            comp_df = pd.read_csv(competitor_csv)
        except Exception as e:
            return pd.DataFrame(), f"⚠️ Failed to read CSV: {e}"
    elif sheet_name:
        comp_df = get_sheet_data(sheet_name)
        if comp_df is None or comp_df.empty:
            return pd.DataFrame(), "⚠️ No competitor data found in sheet."
    else:
        return pd.DataFrame(), "⚠️ Provide either a CSV file or a sheet name for competitor data."

    required_cols = ["Make","Model","Year","Price","Mileage","Fuel","Transmission"]
    for col in required_cols:
        if col not in comp_df.columns:
            comp_df[col] = None

    if "Price" in comp_df.columns:
        comp_df["Price_numeric"] = pd.to_numeric(comp_df["Price"].replace('£','',regex=True), errors='coerce')

    summary = {
        "Total_Competitors": len(comp_df),
        "Avg_Price": round(comp_df["Price_numeric"].mean(),2) if "Price_numeric" in comp_df.columns else 0,
        "Min_Price": round(comp_df["Price_numeric"].min(),2) if "Price_numeric" in comp_df.columns else 0,
        "Max_Price": round(comp_df["Price_numeric"].max(),2) if "Price_numeric" in comp_df.columns else 0,
        "Most_Common_Make": comp_df["Make"].mode()[0] if not comp_df["Make"].empty else None,
        "Most_Common_Model": comp_df["Model"].mode()[0] if not comp_df["Model"].empty else None
    }

    return comp_df, summary

# -------------------------------
# Auto-Scheduled Weekly Content Calendar
# -------------------------------
def generate_weekly_content_calendar(user_email, plan="pro"):
    df_inventory = get_inventory_for_user(user_email)
    if df_inventory.empty:
        return pd.DataFrame(), "⚠️ No inventory available to schedule posts."
    df_inventory["Date"] = pd.to_datetime(df_inventory.get("Timestamp", datetime.utcnow()))
    sm_df = get_social_media_data(user_email)
    if not sm_df.empty and "Date" in sm_df.columns and "Engagement" in sm_df.columns:
        sm_df["Date"] = pd.to_datetime(sm_df["Date"], errors="coerce")
        sm_df["Weekday"] = sm_df["Date"].dt.day_name()
        engagement_by_day = sm_df.groupby("Weekday")["Engagement"].sum().reindex([
            "Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"
        ]).fillna(0)
        best_days = engagement_by_day.sort_values(ascending=False).index.tolist()
    else:
        best_days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

    calendar = []
    start_date = datetime.utcnow()
    for i, (_, row) in enumerate(df_inventory.iterrows()):
        post_day = start_date + timedelta(days=i % 7)
        calendar.append({
            "Date": post_day.date(),
            "Weekday": post_day.strftime("%A"),
            "Car": f"{row.get('Year','')} {row.get('Make','')} {row.get('Model','')}",
            "Content_Type": "Listing Update" if plan.lower() == "pro" else "Listing Update + Social Media Post",
            "Notes": row.get("Notes","")
        })

    return pd.DataFrame(calendar), "✅ Weekly content calendar generated successfully."
