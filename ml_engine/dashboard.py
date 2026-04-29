import sys
import json
import os
import pandas as pd

def get_dashboard_stats():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, 'finalData.csv')
    
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        return {"error": "finalData.csv not found."}

    df.columns = df.columns.str.strip()
    COL_GENRE = 'Genre'
    COL_PRICE = 'Price'
    COL_DATE = 'Released Date'
    COL_RATING = 'Rating'

    # 1. Top Metrics
    total_games = len(df)
    avg_rating = df[COL_RATING].mean()
    top_genre = df[COL_GENRE].mode()[0]

    # 2. Genre Distribution (Top 6 Genres for Bar Chart)
    genre_counts = df[COL_GENRE].value_counts().head(6)
    genre_labels = genre_counts.index.tolist()
    genre_data = genre_counts.values.tolist()

    # 3. Pricing Trends (Average price by Release Year)
    df['Year'] = pd.to_datetime(df[COL_DATE], errors='coerce').dt.year
    valid_years_df = df.dropna(subset=['Year']).copy()
    
    yearly_prices = valid_years_df.groupby('Year')[COL_PRICE].mean().tail(6)
    trend_labels = [str(int(year)) for year in yearly_prices.index.tolist()]
    trend_data = [round(price, 2) for price in yearly_prices.values.tolist()]

    # 4. REAL Genre Growth Over Time (Top 2 Genres)
    top_2_genres = genre_labels[:2] 
    genre1, genre2 = top_2_genres[0], top_2_genres[1]
    
    recent_years = sorted(valid_years_df['Year'].unique())[-6:]
    chart_labels = [str(int(y)) for y in recent_years]
    
    genre1_data = []
    genre2_data = []
    
    for y in recent_years:
        g1_count = len(valid_years_df[(valid_years_df['Year'] == y) & (valid_years_df[COL_GENRE] == genre1)])
        g2_count = len(valid_years_df[(valid_years_df['Year'] == y) & (valid_years_df[COL_GENRE] == genre2)])
        genre1_data.append(g1_count)
        genre2_data.append(g2_count)

    # Safely calculate market growth
    market_growth_str = "+0.0%"
    if len(trend_data) >= 2 and trend_data[0] > 0:
        growth_calc = ((trend_data[-1] - trend_data[0]) / trend_data[0]) * 100
        sign = "+" if growth_calc > 0 else ""
        market_growth_str = f"{sign}{growth_calc:.1f}%"

    return {
        "metrics": {
            "total_games": f"{total_games:,}",
            "average_rating": f"{avg_rating:.1f}",
            "top_genre": str(top_genre),
            "risk_indicator": "Medium",
            "market_growth": market_growth_str,
            "average_price": f"${df[COL_PRICE].mean():.2f}"
        },
        "genre_distribution": {
            "labels": genre_labels,
            "data": genre_data
        },
        "pricing_trends": {
            "labels": trend_labels,
            "data": trend_data
        },
        "chart_data": {
            "labels": chart_labels,
            "genre1_name": genre1,
            "genre1_data": genre1_data,
            "genre2_name": genre2,
            "genre2_data": genre2_data
        }
    }

# THIS IS THE TRIGGER BLOCK THAT WAS MISSING!
if __name__ == "__main__":
    try:
        print(json.dumps(get_dashboard_stats()))
    except Exception as e:
        print(json.dumps({"error": str(e)}))