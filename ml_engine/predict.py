import sys
import json
import os
import pandas as pd
from datetime import datetime

def predict_success(genre, price, platform, release_date):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, 'finalData.csv')
    
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        return {"error": "finalData.csv not found."}

    df.columns = df.columns.str.strip()
    user_price = float(price)
    
    # Extract month from the user's release date (Format: YYYY-MM-DD)
    try:
        release_month = datetime.strptime(release_date, "%Y-%m-%d").month
    except ValueError:
        release_month = 6 # Fallback to summer if date is invalid

    # 1. Filter dataset by the requested genre
    genre_data = df[df['Genre'].str.contains(genre, case=False, na=False)].copy()
    
    if genre_data.empty:
        return {
            "success_probability": "50%",
            "risk_level": "High",
            "recommendation": "Insufficient market data for this genre to make a confident prediction."
        }

    # 2. Extract release months from historical data for seasonality check
    genre_data['Month'] = pd.to_datetime(genre_data['Released Date'], errors='coerce').dt.month
    
    # 3. The Math: Calculate base probability from historical ratings
    avg_genre_rating = genre_data['Rating'].mean()
    base_prob = (avg_genre_rating / 10.0) * 100 # Assuming 10 is max rating based on your CSV

    # 4. Price Analysis
    avg_price = genre_data['Price'].mean()
    price_diff = user_price - avg_price
    
    if user_price <= avg_price:
        base_prob += 10 # Competitive pricing bonus
    elif user_price > avg_price * 1.5:
        base_prob -= 20 # Severe overpricing penalty
    else:
        base_prob -= (price_diff / avg_price) * 15 # Gradual penalty

    # 5. Seasonality Analysis (Does this genre do well in this month?)
    month_data = genre_data[genre_data['Month'] == release_month]
    if not month_data.empty:
        month_avg_rating = month_data['Rating'].mean()
        if month_avg_rating > avg_genre_rating:
            base_prob += 5 # Good release window bonus
        else:
            base_prob -= 5 # Poor release window penalty

    # Cap probability between 15% and 98%
    final_score = min(max(int(base_prob), 15), 98)
    risk_level = "Low" if final_score > 75 else "Medium" if final_score > 50 else "High"
    
    return {
        "success_probability": f"{final_score}%",
        "risk_level": risk_level,
        "recommendation": f"The average {genre} game costs ${avg_price:.2f}. Your pricing and release window put this project at {risk_level.lower()} risk."
    }

if __name__ == "__main__":
    if len(sys.argv) >= 5:
        genre = sys.argv[1]
        price = sys.argv[2]
        platform = sys.argv[3]
        release_date = sys.argv[4] # New parameter
        result = predict_success(genre, price, platform, release_date)
        print(json.dumps(result))
    else:
        print(json.dumps({"error": "Missing parameters for prediction."}))