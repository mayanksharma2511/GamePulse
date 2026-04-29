import sys
import json
import os
import pandas as pd
import re
from collections import Counter

# Custom NLP algorithm to extract defining tags from a paragraph
def extract_keywords(plot_text):
    if not isinstance(plot_text, str) or plot_text.lower() == 'nan':
        return ["Action", "Adventure"] # Fallback tags
    
    # Words we don't care about
    stopwords = {"the", "and", "that", "for", "with", "from", "this", "game", "player", "players", "their", "which", "have", "they", "will", "into", "through", "character", "characters", "about"}
    
    # Extract only words longer than 3 letters
    words = re.findall(r'\b[a-z]{4,}\b', plot_text.lower())
    
    # Filter and count the most common meaningful words
    filtered = [w for w in words if w not in stopwords]
    most_common = Counter(filtered).most_common(3)
    
    # Capitalize them for the UI
    return [word[0].capitalize() for word in most_common]

def get_recommendations(target_name):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, 'finalData.csv')
    
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        return {"error": "finalData.csv not found in the ml_engine folder."}

    df.columns = df.columns.str.strip()
    COL_NAME = 'Title'
    COL_GENRE = 'Genre'
    COL_PRICE = 'Price'
    COL_RATING = 'Rating'
    COL_PUBLISHER = 'Publisher'
    COL_PLOTS = 'Plots' # The column we are mining

    target_game_row = df[df[COL_NAME].str.lower() == target_name.lower()]
    
    if target_game_row.empty:
        return {"error": f"Game '{target_name}' not found in the database."}
    
    target_genre = target_game_row.iloc[0][COL_GENRE]
    
    similar_games = df[(df[COL_GENRE] == target_genre) & (df[COL_NAME].str.lower() != target_name.lower())].copy()
    similar_games = similar_games.sort_values(by=COL_RATING, ascending=False).head(6)

    results = []
    for _, row in similar_games.iterrows():
        match_percentage = min(int(float(row[COL_RATING]) * 10 + 15), 99) 
        
        # Run our NLP Extractor on the storyline!
        smart_tags = extract_keywords(str(row.get(COL_PLOTS, '')))
        
        results.append({
            "title": str(row[COL_NAME]),
            "match": f"{match_percentage}%",
            "genre": str(row[COL_GENRE]),
            "price": f"${float(row[COL_PRICE]):.2f}",
            "rating": f"{float(row[COL_RATING]):.1f}",
            "publisher": str(row[COL_PUBLISHER]),
            "tags": smart_tags # Sending the tags to the UI
        })
        
    return results

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_game = sys.argv[1]
        results = get_recommendations(target_game)
        print(json.dumps(results))
    else:
        print(json.dumps({"error": "No game name provided"}))