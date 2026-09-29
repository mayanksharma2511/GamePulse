import sys
import json
import os
import pandas as pd
from datetime import datetime


def predict_score(genre, price, release_date):
    """Rule-based score built from the historical ratings of games in one genre.

    This is a heuristic, not a trained model: the adjustments (+10, -20, +/-5)
    are fixed by hand. See the README for how it works and its limitations.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, 'finalData.csv')

    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        return {"error": "finalData.csv not found."}

    df.columns = df.columns.str.strip()

    try:
        user_price = float(price)
    except ValueError:
        return {"error": "Price must be a number."}

    try:
        release_month = datetime.strptime(release_date, "%Y-%m-%d").month
    except ValueError:
        return {"error": "Release date must be in YYYY-MM-DD format."}

    # 1. Games in exactly the chosen genre
    genre_data = df[df['Genre'].str.lower() == genre.lower()].copy()
    if genre_data.empty:
        return {"error": f"No games in the dataset have the genre '{genre}'."}

    genre_data['Month'] = pd.to_datetime(genre_data['Released Date'], errors='coerce').dt.month

    # 2. Base score: the genre's average rating as a percentage
    avg_genre_rating = genre_data['Rating'].mean()
    score = (avg_genre_rating / 10.0) * 100

    # 3. Price adjustment against the genre's average price
    avg_price = genre_data['Price'].mean()
    if user_price <= avg_price:
        score += 10
    elif user_price > avg_price * 1.5:
        score -= 20
    else:
        score -= ((user_price - avg_price) / avg_price) * 15

    # 4. Release-month adjustment
    month_data = genre_data[genre_data['Month'] == release_month]
    if not month_data.empty:
        score += 5 if month_data['Rating'].mean() > avg_genre_rating else -5

    final_score = min(max(int(score), 15), 98)
    risk_level = "Low" if final_score > 75 else "Medium" if final_score > 50 else "High"

    return {
        "score": final_score,
        "risk_level": risk_level,
        "games_in_genre": int(len(genre_data)),
        "games_in_month": int(len(month_data)),
        "explanation": (
            f"Based on {len(genre_data)} {genre} games (average rating {avg_genre_rating:.1f}/10, "
            f"average price ${avg_price:.2f}), of which {len(month_data)} were released in the same month."
        ),
    }


if __name__ == "__main__":
    if len(sys.argv) >= 4:
        print(json.dumps(predict_score(sys.argv[1], sys.argv[2], sys.argv[3])))
    else:
        print(json.dumps({"error": "Expected genre, price and release date."}))
