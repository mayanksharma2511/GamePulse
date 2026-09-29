import json
import os
import sys
from datetime import datetime

MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def load_model():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model.json")
    with open(path) as f:
        return json.load(f)


def predict_rating(genre_group, publisher, price, release_date):
    """Estimate a game's rating out of 10 with an 80% range.

    Uses the ridge regression exported by analysis/train_model.py. Each input's
    contribution is shown relative to an average game in the training data.
    """
    m = load_model()

    if genre_group not in m["categorical"]["genre_group"]:
        return {"error": f"Unknown genre group '{genre_group}'."}
    try:
        price = float(price)
    except ValueError:
        return {"error": "Price must be a number."}
    if price < 0:
        return {"error": "Price cannot be negative."}
    try:
        month = datetime.strptime(release_date, "%Y-%m-%d").month
    except ValueError:
        return {"error": "Release date must be in YYYY-MM-DD format."}

    pub = None if publisher.strip().lower() in ("", "unknown") else m["publishers"].get(publisher.strip())
    publisher_value = pub["history"] if pub else m["overall_average_rating"]
    publisher_games = pub["games"] if pub else 0

    inputs = {"genre_group": genre_group, "release_month": str(month),
              "Price": price, "price_imputed": 0.0, "publisher_history": publisher_value}

    # Prediction = average game + each input's contribution
    contributions = {}
    for f in ["genre_group", "release_month"]:
        coef = m["categorical"][f].get(inputs[f], 0.0)
        contributions[f] = coef - m["categorical_training_average"][f]
    for f, p in m["numeric"].items():
        contributions[f] = p["coef"] * (inputs[f] - p["mean"]) / p["scale"]

    average_game = m["intercept"] + sum(m["categorical_training_average"].values())
    estimate = average_game + sum(contributions.values())
    half = m["interval_half_width"]

    labels = {
        "genre_group": f"Genre group: {genre_group}",
        "release_month": f"Release month: {MONTHS[month]}",
        "Price": f"Price: ${price:.2f}",
        "publisher_history": (f"Publisher: {publisher.strip()} ({publisher_games} rated games in training data)"
                              if pub else "Publisher: no rated games in training data"),
    }
    factors = [{"factor": labels[f], "effect": round(v, 2)}
               for f, v in contributions.items() if f in labels]
    factors.sort(key=lambda x: abs(x["effect"]), reverse=True)

    return {
        "estimate": round(estimate, 1),
        "range_low": round(max(0.0, estimate - half), 1),
        "range_high": round(min(10.0, estimate + half), 1),
        "coverage": m["coverage_target"],
        "average_game": round(average_game, 2),
        "factors": factors,
        "genre_group_games": m["genre_group_games"].get(genre_group, 0),
        "publisher_games": publisher_games,
        "model": m["trained_on"],
        "tested_coverage": m["tested_coverage"],
        "tested_on": m["tested_on"],
    }


if __name__ == "__main__":
    if len(sys.argv) >= 5:
        print(json.dumps(predict_rating(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])))
    else:
        print(json.dumps({"error": "Expected genre group, publisher, price and release date."}))
