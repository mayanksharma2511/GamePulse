"""Launch Planner: estimates for a game that has not been released yet.

Uses the models built by steam_analysis/train_models.py (ml_engine/steam_models.joblib).

    python3 launch_planner.py options             form options and the models' measured accuracy
    python3 launch_planner.py estimate '<json>'   estimates for one game
    python3 launch_planner.py market              Steam market statistics for the overview page
"""
import json
import os
import sys

import joblib
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "steam_analysis"))
from features import split, tabular  # noqa: E402
from train_models import neighbours, reach_pred, reception_logit  # noqa: E402

MODELS = os.path.join(HERE, "steam_models.joblib")
DATA = os.path.join(ROOT, "steam_analysis", "data", "steam_games.csv")
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]


def load():
    return joblib.load(MODELS)


def options():
    m = load()
    return {
        "genres": m["genre_options"],
        "categories": m["category_options"],
        "months": MONTHS,
        "coverage": m["coverage"],
        "trained_on": m["trained_on"],
        "checks": m["checks"],
    }


def studio(m, kind, name):
    name = (name or "").strip()
    records = m["studios"][kind]
    match = records.get(name) or next((v for k, v in records.items() if k.lower() == name.lower()), None)
    rec = match or m["studios"]["default"]
    return rec, bool(match), name


def estimate(payload: dict):
    m = load()
    description = str(payload.get("description", "")).strip()
    if len(description) < 20:
        return {"error": "Please describe the game in at least a sentence (20+ characters)."}
    try:
        price = float(payload.get("price", 0))
    except (TypeError, ValueError):
        return {"error": "Price must be a number."}
    if price < 0:
        return {"error": "Price cannot be negative."}
    month = int(payload.get("releaseMonth", 1))
    if not 1 <= month <= 12:
        return {"error": "Release month must be between 1 and 12."}
    genres = [g for g in payload.get("genres", []) if g in m["genre_options"]]
    if not genres:
        return {"error": "Please choose at least one genre."}
    categories = [c for c in payload.get("categories", []) if c in m["category_options"]]

    dev, dev_known, dev_name = studio(m, "developer", payload.get("developer"))
    pub_name_raw = (payload.get("publisher") or "").strip() or dev_name
    pub, pub_known, pub_name = studio(m, "publisher", pub_name_raw)

    row = pd.DataFrame([{
        "price": price, "is_free": int(price == 0), "mac": int(bool(payload.get("mac"))),
        "linux": int(bool(payload.get("linux"))), "age_restricted": int(bool(payload.get("ageRestricted"))),
        "english": 1, "release_month": month,
        "genres": ";".join(genres), "categories": ";".join(categories),
        "developer_prior_games": dev["games"], "developer_prior_reach": dev["reach"], "developer_prior_vp": dev["vp"],
        "publisher_prior_games": pub["games"], "publisher_prior_reach": pub["reach"], "publisher_prior_vp": pub["vp"],
        "self_published": int(dev_name.lower() == pub_name.lower() if dev_name else 1),
        "short_description": description,
    }])

    # Reception probability (recalibrated logistic regression)
    r = m["reception"]
    a, b = r["recalibration"]
    logit = float(reception_logit(r, row)[0])
    prob = 1 / (1 + np.exp(-(a * logit + b)))

    # What moved the estimate, relative to an average training game (in log-odds)
    X = tabular(row, r["vocab"], True)[r["columns"]]
    z = r["scaler"].transform(X)[0]
    coefs = r["model"].coef_[0]
    n_tab = len(r["columns"])
    contrib = pd.Series(a * coefs[:n_tab] * z, index=r["columns"])
    text_vec = r["vectorizer"].transform([description])
    text_effect = float(a * ((text_vec @ coefs[n_tab:])[0] - r["text_mean"]))

    def label(col):
        if col.startswith("genre: "):
            # Only genres the game has are shown; "not an Action game" is not something to act on
            name = col.split(": ", 1)[1]
            return f"{name} genre" if X[col].iloc[0] else None
        if col.startswith("category: "):
            name = col.split(": ", 1)[1]
            return name if X[col].iloc[0] else f"No {name}"
        names = {
            "price": f"Price ${price:.2f}", "log_price": f"Price ${price:.2f}", "is_free": f"Price ${price:.2f}",
            "mac": "Mac version" if row["mac"][0] else "No Mac version",
            "linux": "Linux version" if row["linux"][0] else "No Linux version",
            "age_restricted": "Age restricted" if row["age_restricted"][0] else "No age restriction",
            "developer_prior_games_log": "Developer's experience",
            "developer_prior_reach": "Developer's past reach",
            "developer_prior_vp": "Developer's past reviews",
            "publisher_prior_games_log": "Publisher's experience",
            "publisher_prior_reach": "Publisher's past reach",
            "publisher_prior_vp": "Publisher's past reviews",
            "self_published": "Self-published" if row["self_published"][0] else "Separate publisher",
        }
        # For a studio with no earlier games, its "record" is just the average, so only
        # its lack of experience is shown
        if col.startswith("developer_prior") and not dev_known:
            return "New developer" if col == "developer_prior_games_log" else None
        if col.startswith("publisher_prior") and not pub_known:
            return "New publisher" if col == "publisher_prior_games_log" else None
        if col.startswith("month_"):
            return f"Release in {MONTHS[int(col.split('_')[1]) - 1]}" if X[col].iloc[0] else None
        return names.get(col, col)

    grouped = {}
    for col, v in contrib.items():
        name = label(col)
        if name and abs(v) > 1e-9:
            grouped[name] = grouped.get(name, 0.0) + float(v)
    grouped["Description wording"] = text_effect
    factors = sorted(({"factor": k, "effect": round(v, 3)} for k, v in grouped.items()),
                     key=lambda f: abs(f["effect"]), reverse=True)[:10]

    # Reach (gradient boosting + conformal range)
    reach = float(reach_pred(m["reach"], row)[0])
    half = m["reach"]["half_width"]
    lo, hi = max(0.0, reach - half), min(100.0, reach + half)
    ref = m["reach_reference"]

    def reviews_at(p):
        return min(ref, key=lambda x: abs(x["percentile"] - p))["reviews"]

    # Comparable games
    comp = m["comparables"]
    idx, sims = neighbours(comp, [description], k=8)
    games = comp["games"].iloc[idx[0]]
    comparables = [{
        "name": g["name"], "year": int(g["release_year"]), "price": round(float(g["price"]), 2),
        "positive_share": round(float(g["positive_share"]) * 100),
        "reviews": int(g["total_reviews"]), "owners": g["owners"],
        "tags": split(g["steamspy_tags"])[:3], "similarity": round(float(s), 2),
        "url": f"https://store.steampowered.com/app/{int(g['appid'])}",
    } for (_, g), s in zip(games.iterrows(), sims[0])]

    return {
        "reception": {"probability": round(float(prob), 3), "factors": factors,
                      "typical": round(m["typical_very_positive"], 3)},
        "reach": {"estimate": round(reach), "low": round(lo), "high": round(hi),
                  "reviews_estimate": reviews_at(reach), "reviews_low": reviews_at(lo), "reviews_high": reviews_at(hi)},
        "comparables": comparables,
        "studios": {
            "developer": {"name": dev_name or "Not given", "known": dev_known, "games": dev["games"]},
            "publisher": {"name": pub_name or "Not given", "known": pub_known, "games": pub["games"]},
        },
        "coverage": m["coverage"],
        "checks": m["checks"],
        "trained_on": m["trained_on"],
    }


def market():
    df = pd.read_csv(DATA, usecols=["release_year", "genres", "price", "very_positive", "total_reviews", "in_study"])
    study = df[df["in_study"]]
    rated = study[study["very_positive"].notna()]
    per_year = study.groupby("release_year").size()

    genre_rows = []
    for g in sorted({x for v in rated["genres"] for x in split(v)}):
        sub = rated[rated["genres"].map(lambda v: g in split(v))]
        if len(sub) >= 200 and g not in {"Indie", "Early Access", "Free to Play"}:
            genre_rows.append((g, len(sub), float(sub["very_positive"].mean())))
    genre_rows.sort(key=lambda x: -x[2])

    bands = [("Free", 0, 0), ("Under $5", 0.01, 4.99), ("$5–9.99", 5, 9.99), ("$10–19.99", 10, 19.99),
             ("$20 and up", 20, 1e9)]
    price_rows = []
    for name, lo, hi in bands:
        sub = rated[(rated["price"] >= lo) & (rated["price"] <= hi)]
        price_rows.append((name, len(sub), float(sub["very_positive"].mean())))

    paid = study[study["price"] > 0]["price"]
    return {
        "metrics": {
            "games_total": f"{len(df):,}",
            "games_study": f"{len(study):,}",
            "very_positive_rate": f"{rated['very_positive'].mean():.1%}",
            "median_paid_price": f"${paid.median():.2f}",
        },
        "per_year": {"labels": [str(int(y)) for y in per_year.index], "data": per_year.astype(int).tolist()},
        "genre_vp": {"labels": [f"{g} (n={n:,})" for g, n, _ in genre_rows],
                     "data": [round(v * 100, 1) for _, _, v in genre_rows]},
        "price_vp": {"labels": [f"{b} (n={n:,})" for b, n, _ in price_rows],
                     "data": [round(v * 100, 1) for _, _, v in price_rows]},
    }


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if cmd == "options":
            out = options()
        elif cmd == "estimate":
            out = estimate(json.loads(sys.argv[2]))
        elif cmd == "market":
            out = market()
        else:
            out = {"error": "Unknown command."}
    except Exception as e:  # report errors as JSON so the API can show them
        out = {"error": f"{type(e).__name__}: {e}"}
    print(json.dumps(out))
