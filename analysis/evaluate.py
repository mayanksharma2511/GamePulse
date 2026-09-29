"""Evaluate how well different methods predict a game's rating.

Uses analysis/clean_games.csv (run analysis/data_audit.py first) and only the rows
with an original rating and a known release year.

Time-based split: methods learn from games released up to TRAIN_UNTIL and are
tested on games released afterwards, which mimics predicting future releases.
Model settings are fixed in advance (not tuned on the test set).

Outputs:
    analysis/results.csv     - one row per method
    analysis/EVALUATION.md   - the same results as a short report

Run from the repository root:
    python3 analysis/evaluate.py
"""
import os

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "analysis", "clean_games.csv")
OUT_DIR = os.path.join(ROOT, "analysis")

TRAIN_UNTIL = 2019
N_BOOTSTRAP = 2000
SEED = 0


def heuristic_score(genre, price, month, train):
    """The original GamePulse rule (ml_engine/predict.py), using training data only.

    Returns the score divided by 10 so it is on the same 0-10 scale as ratings,
    or NaN if no training game has this exact genre.
    """
    g = train[train["Genre"].str.lower() == str(genre).lower()]
    if g.empty:
        return np.nan
    avg_rating = g["Rating"].mean()
    score = avg_rating * 10
    avg_price = g["Price"].mean()
    if price <= avg_price:
        score += 10
    elif price > avg_price * 1.5:
        score -= 20
    else:
        score -= (price - avg_price) / avg_price * 15
    same_month = g[g["release_month"] == month]
    if not same_month.empty:
        score += 5 if same_month["Rating"].mean() > avg_rating else -5
    return min(max(int(score), 15), 98) / 10


def publisher_history(train, test, smoothing=5):
    """Each publisher's average rating in the training data, shrunk towards the
    overall average when the publisher has few games. Computed from training
    games only, so no test ratings leak into the feature."""
    overall = train["Rating"].mean()
    stats = train.groupby("Publisher")["Rating"].agg(["mean", "count"])
    shrunk = (stats["mean"] * stats["count"] + overall * smoothing) / (stats["count"] + smoothing)
    # For training rows, leave each game out of its own publisher average
    sums = train.groupby("Publisher")["Rating"].transform("sum")
    counts = train.groupby("Publisher")["Rating"].transform("count")
    loo_mean = (sums - train["Rating"]) / (counts - 1).replace(0, np.nan)
    loo_count = counts - 1
    train_feat = ((loo_mean.fillna(overall) * loo_count + overall * smoothing) / (loo_count + smoothing))
    test_feat = test["Publisher"].map(shrunk).fillna(overall)
    return train_feat.values, test_feat.values


def bootstrap_mae_ci(y, pred, rng):
    """95% bootstrap interval for the mean absolute error."""
    errors = np.abs(y - pred)
    means = [rng.choice(errors, size=len(errors), replace=True).mean() for _ in range(N_BOOTSTRAP)]
    return np.percentile(means, [2.5, 97.5])


def paired_difference(y, pred, baseline, rng):
    """MAE of `pred` minus MAE of `baseline` on the same games, with a 95% paired
    bootstrap interval (both methods are resampled on the same games each time)."""
    diff = np.abs(y - pred) - np.abs(y - baseline)
    means = [rng.choice(diff, size=len(diff), replace=True).mean() for _ in range(N_BOOTSTRAP)]
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(diff.mean()), float(lo), float(hi)


def main() -> None:
    df = pd.read_csv(DATA)
    df = df[df["usable_for_evaluation"]].copy()
    df["release_month"] = df["release_month"].fillna(0)  # 0 = month unknown
    df["Publisher"] = df["Publisher"].fillna("Unknown")

    train = df[df["release_year"] <= TRAIN_UNTIL].copy()
    test = df[df["release_year"] > TRAIN_UNTIL].copy()
    y_train, y_test = train["Rating"].values, test["Rating"].values

    train["publisher_history"], test["publisher_history"] = publisher_history(train, test)

    predictions = {}

    # Baselines
    predictions["Overall average rating"] = np.full(len(test), y_train.mean())
    group_means = train.groupby("genre_group")["Rating"].mean()
    predictions["Genre-group average rating"] = test["genre_group"].map(group_means).fillna(y_train.mean()).values

    # The original GamePulse heuristic
    predictions["Original GamePulse score (/10)"] = np.array([
        heuristic_score(g, p, m, train) for g, p, m in zip(test["Genre"], test["Price"], test["release_month"])
    ])

    # Learned models
    categorical = ["genre_group", "release_month"]
    basic_numeric = ["Price", "price_imputed"]
    feature_sets = {
        "basic": basic_numeric,
        "basic + publisher history": basic_numeric + ["publisher_history"],
    }
    for set_name, numeric in feature_sets.items():
        cols = categorical + numeric
        prep = ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical),
            ("num", StandardScaler(), numeric),
        ])
        models = {
            "Ridge regression": Ridge(alpha=10.0),
            "Gradient boosting": HistGradientBoostingRegressor(
                max_depth=3, max_iter=200, learning_rate=0.05, random_state=SEED),
        }
        for model_name, model in models.items():
            pipe = make_pipeline(clone(prep), model)
            pipe.fit(train[cols], y_train)
            predictions[f"{model_name} ({set_name})"] = pipe.predict(test[cols])

    # Score every method on the same test games
    rng = np.random.default_rng(SEED)
    baseline_pred = predictions["Overall average rating"]
    rows = []
    for name, pred in predictions.items():
        ok = ~np.isnan(pred)
        y, p = y_test[ok], pred[ok]
        lo, hi = bootstrap_mae_ci(y, p, rng)
        d_mean, d_lo, d_hi = paired_difference(y, p, baseline_pred[ok], rng)
        rho = spearmanr(p, y)[0] if np.ptp(p) > 1e-9 else np.nan
        rows.append({
            "method": name,
            "test_games_scored": int(ok.sum()),
            "mae": round(float(np.mean(np.abs(y - p))), 3),
            "mae_ci_low": round(float(lo), 3),
            "mae_ci_high": round(float(hi), 3),
            "spearman_rho": None if np.isnan(rho) else round(float(rho), 3),
            "mae_minus_baseline": round(d_mean, 3),
            "diff_ci_low": round(d_lo, 3),
            "diff_ci_high": round(d_hi, 3),
        })
    results = pd.DataFrame(rows)
    results.to_csv(os.path.join(OUT_DIR, "results.csv"), index=False)

    baseline_mae = results.loc[results["method"] == "Overall average rating", "mae"].iloc[0]
    table = "\n".join(
        f"| {r.method} | {r.test_games_scored} | {r.mae:.3f} ({r.mae_ci_low:.3f}–{r.mae_ci_high:.3f}) | "
        f"{'—' if pd.isna(r.spearman_rho) else f'{r.spearman_rho:.3f}'} | "
        f"{'—' if r.method == 'Overall average rating' else f'{r.mae_minus_baseline:+.3f} ({r.diff_ci_low:+.3f} to {r.diff_ci_high:+.3f})'} |"
        for r in results.itertuples()
    )
    best = results.sort_values("mae").iloc[0]
    report = f"""# Evaluation: predicting a game's rating

Generated by `analysis/evaluate.py` from `analysis/clean_games.csv`.

## Setup

- **Data:** {len(df)} games with an original (not filled-in) rating and a known release year.
- **Split by time:** methods learn from {len(train)} games released {int(train['release_year'].min())}–{TRAIN_UNTIL}
  and are tested on {len(test)} games released {TRAIN_UNTIL + 1}–{int(test['release_year'].max())}.
- **Metrics:** mean absolute error (MAE, in rating points out of 10; lower is better) with a 95%
  bootstrap interval, and Spearman's ρ (how well the method ranks games; 0 means no relationship).
- **Features for learned models:** genre group, release month, price, and whether the price was filled
  in; the second set adds the publisher's average rating in the training data. Release year is left out
  because every test year lies outside the training years.
- **Compared with the baseline:** the difference in MAE against always predicting the overall average,
  with a 95% paired bootstrap interval. An interval that includes 0 means the method is not clearly
  better or worse than the baseline on this test set.
- The original score is divided by 10 to put it on the rating scale. It can only score test games
  whose exact genre appears in the training data.

## Results

| Method | Test games | MAE (95% interval) | Spearman ρ | MAE vs. baseline (95% interval) |
|---|---|---|---|---|
{table}

Lowest error: **{best['method']}** (MAE {best['mae']:.3f}). Always predicting the overall
average gives MAE {baseline_mae:.3f}.
"""
    with open(os.path.join(OUT_DIR, "EVALUATION.md"), "w") as f:
        f.write(report)
    print(report)


if __name__ == "__main__":
    main()
