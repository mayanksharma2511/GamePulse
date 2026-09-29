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

    # Prices and ratings with more than two decimals were filled in with averages
    # (see analysis/DATA_AUDIT.md), so averages below use original values only.
    def is_filled_in(x):
        return abs(round(x, 2) - x) > 1e-6
    real_price = ~df[COL_PRICE].map(is_filled_in)
    real_rating = ~df[COL_RATING].map(is_filled_in)

    # 1. Top Metrics
    total_games = len(df)
    avg_rating = df.loc[real_rating, COL_RATING].mean()
    top_genre = df[COL_GENRE].mode()[0]

    # 2. Genre Distribution (Top 6 Genres for Bar Chart)
    genre_counts = df[COL_GENRE].value_counts().head(6)
    genre_labels = genre_counts.index.tolist()
    genre_data = genre_counts.values.tolist()

    # 3. Pricing Trends (Average price by Release Year)
    df['Year'] = pd.to_datetime(df[COL_DATE], errors='coerce').dt.year
    valid_years_df = df.dropna(subset=['Year']).copy()
    
    priced = valid_years_df[real_price.loc[valid_years_df.index]]
    yearly = priced.groupby('Year')[COL_PRICE].agg(['mean', 'count'])
    yearly = yearly[yearly['count'] >= 50].tail(6)  # skip years with too few games to average
    trend_labels = [f"{int(y)} (n={int(n)})" for y, n in zip(yearly.index, yearly['count'])]
    trend_data = [round(v, 2) for v in yearly['mean'].tolist()]
    trend_years = [str(int(y)) for y in yearly.index]

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

    # Change in average price between the first and last of those years
    price_change_str = "n/a"
    if len(trend_data) >= 2 and trend_data[0] > 0:
        change = ((trend_data[-1] - trend_data[0]) / trend_data[0]) * 100
        sign = "+" if change > 0 else ""
        price_change_str = f"{sign}{change:.1f}% ({trend_years[0]}-{trend_years[-1]})"

    return {
        "metrics": {
            "total_games": f"{total_games:,}",
            "average_rating": f"{avg_rating:.1f}",
            "top_genre": str(top_genre),
            "avg_price_change": price_change_str,
            "average_price": f"${df.loc[real_price, COL_PRICE].mean():.2f}",
            "games_with_original_price": int(real_price.sum())
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

if __name__ == "__main__":
    try:
        print(json.dumps(get_dashboard_stats()))
    except Exception as e:
        print(json.dumps({"error": str(e)}))