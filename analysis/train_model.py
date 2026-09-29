"""Train the rating model used by the app, with an 80% prediction range.

Model: ridge regression on genre group, release month, price, whether the price was
filled in, and the publisher's average rating in the training data (the best
method in analysis/EVALUATION.md). Ranges use split conformal prediction: the
model is fitted on one set of games, and the size of its errors on a later,
separate set of games sets the width of the range.

1. Check the method: fit on games up to 2018, calibrate on 2019, and test on
   2020-2023 whether the range contains the real rating about 80% of the time.
2. Build the version 2 app's model the same way on more recent data: fit on games
   up to 2020 and calibrate on 2021-2023. Export it to analysis/model.json as plain
   numbers. (Version 3 replaced this app with the Steam-based Launch Planner.)

Outputs: analysis/model.json, analysis/INTERVALS.md, analysis/interval_results.csv

Run from the repository root (after analysis/data_audit.py):
    python3 analysis/train_model.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evaluate import publisher_history  # noqa: E402  (same feature as in the evaluation)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "analysis", "clean_games.csv")
MODEL_OUT = os.path.join(ROOT, "analysis", "model.json")

COVERAGE = 0.80
CATEGORICAL = ["genre_group", "release_month"]
NUMERIC = ["Price", "price_imputed", "publisher_history"]
PUBLISHER_SMOOTHING = 5
KNOWN_PUBLISHER_MIN_GAMES = 3


def load() -> pd.DataFrame:
    df = pd.read_csv(DATA)
    df = df[df["usable_for_evaluation"]].copy()
    df["release_month"] = df["release_month"].fillna(0).astype(int)  # 0 = month unknown
    df["Publisher"] = df["Publisher"].fillna("Unknown")
    df["price_imputed"] = df["price_imputed"].astype(float)
    return df


def fit(train: pd.DataFrame):
    pipe = make_pipeline(
        ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL),
            ("num", StandardScaler(), NUMERIC),
        ]),
        Ridge(alpha=10.0),
    )
    pipe.fit(train[CATEGORICAL + NUMERIC], train["Rating"])
    return pipe


def conformal_quantile(abs_errors: np.ndarray) -> float:
    """Error size that at least COVERAGE of calibration games stay within,
    with the standard finite-sample correction."""
    n = len(abs_errors)
    level = min(1.0, np.ceil((n + 1) * COVERAGE) / n)
    return float(np.quantile(abs_errors, level, method="higher"))


def fit_and_calibrate(train: pd.DataFrame, calib: pd.DataFrame):
    train, calib = train.copy(), calib.copy()
    train["publisher_history"], calib["publisher_history"] = publisher_history(train, calib)
    model = fit(train)
    errors = np.abs(calib["Rating"].values - model.predict(calib[CATEGORICAL + NUMERIC]))
    return model, conformal_quantile(errors), train


def check_method(df: pd.DataFrame) -> dict:
    train = df[df["release_year"] <= 2018]
    calib = df[df["release_year"] == 2019]
    test = df[df["release_year"] >= 2020].copy()
    model, q, train_used = fit_and_calibrate(train, calib)
    _, test["publisher_history"] = publisher_history(train_used, test)
    pred = model.predict(test[CATEGORICAL + NUMERIC])
    inside = np.abs(test["Rating"].values - pred) <= q
    known = test["Publisher"].map(train_used["Publisher"].value_counts()).fillna(0) >= KNOWN_PUBLISHER_MIN_GAMES
    return {
        "train_games": len(train), "calibration_games": len(calib), "test_games": len(test),
        "half_width": round(q, 3),
        "coverage": round(float(inside.mean()), 3),
        "coverage_known_publisher": round(float(inside[known.values].mean()), 3),
        "known_publisher_games": int(known.sum()),
        "coverage_other_publisher": round(float(inside[~known.values].mean()), 3),
        "other_publisher_games": int((~known).sum()),
        "test_mae": round(float(np.mean(np.abs(test["Rating"].values - pred))), 3),
    }


def export(model, q: float, train: pd.DataFrame, calib_n: int) -> dict:
    """Write the fitted ridge model as plain numbers."""
    prep, ridge = model.named_steps["columntransformer"], model.named_steps["ridge"]
    enc, scaler = prep.named_transformers_["cat"], prep.named_transformers_["num"]
    coefs = ridge.coef_
    n_cat = sum(len(c) for c in enc.categories_)
    cat_coefs, i = {}, 0
    for feature, cats in zip(CATEGORICAL, enc.categories_):
        cat_coefs[feature] = {str(int(c) if feature == "release_month" else c): float(coefs[i + j])
                              for j, c in enumerate(cats)}
        i += len(cats)
    numeric = {f: {"mean": float(m), "scale": float(s), "coef": float(c)}
               for f, m, s, c in zip(NUMERIC, scaler.mean_, scaler.scale_, coefs[n_cat:])}

    # Average effect of each categorical feature over the training games, so the
    # app can show each input's contribution relative to an average game.
    cat_avg = {f: float(train[f].astype(str).map(cat_coefs[f]).mean()) for f in CATEGORICAL}

    overall = float(train["Rating"].mean())
    stats = train.groupby("Publisher")["Rating"].agg(["mean", "count"])
    shrunk = (stats["mean"] * stats["count"] + overall * PUBLISHER_SMOOTHING) / (stats["count"] + PUBLISHER_SMOOTHING)
    publishers = {p: {"history": round(float(shrunk[p]), 4), "games": int(stats.loc[p, "count"])}
                  for p in stats.index}

    return {
        "description": "Ridge regression predicting a game's rating out of 10. Built by analysis/train_model.py.",
        "trained_on": f"{len(train)} games released {int(train['release_year'].min())}-2020 with original ratings",
        "calibrated_on": f"{calib_n} games released 2021-2023",
        "coverage_target": COVERAGE,
        "interval_half_width": round(q, 4),
        "intercept": float(ridge.intercept_),
        "categorical": cat_coefs,
        "categorical_training_average": cat_avg,
        "numeric": numeric,
        "overall_average_rating": overall,
        "publishers": publishers,
        "genre_group_games": {g: int(n) for g, n in train["genre_group"].value_counts().items()},
    }


def predict_from_json(m: dict, row: dict) -> float:
    """Same calculation as ml_engine/predict.py, used here to check the export."""
    total = m["intercept"]
    for f in CATEGORICAL:
        total += m["categorical"][f].get(str(row[f]), 0.0)
    for f, p in m["numeric"].items():
        total += p["coef"] * (row[f] - p["mean"]) / p["scale"]
    return total


def main() -> None:
    df = load()

    check = check_method(df)
    pd.DataFrame([check]).to_csv(os.path.join(ROOT, "analysis", "interval_results.csv"), index=False)

    train = df[df["release_year"] <= 2020]
    calib = df[df["release_year"] >= 2021]
    model, q, train_used = fit_and_calibrate(train, calib)
    exported = export(model, q, train_used, len(calib))
    exported["tested_coverage"] = check["coverage"]
    exported["tested_on"] = f"{check['test_games']} games released 2020-2023 (method check)"

    # The exported numbers must reproduce the fitted model exactly
    sample = train_used.head(50)
    expected = model.predict(sample[CATEGORICAL + NUMERIC])
    got = [predict_from_json(exported, r) for r in sample.to_dict("records")]
    assert np.allclose(expected, got, atol=1e-6), "Exported model does not match the fitted model"

    with open(MODEL_OUT, "w") as f:
        json.dump(exported, f, indent=1)

    report = f"""# Prediction ranges

Generated by `analysis/train_model.py`.

Every rating estimate in the app comes with an {COVERAGE:.0%} range, built with split conformal
prediction: the model is fitted on one set of games, and the size of its errors on a later,
separate set of games decides how wide the range must be for {COVERAGE:.0%} of games to fall inside it.

## Does the range work?

Fitted on {check['train_games']} games (2017–2018), calibrated on {check['calibration_games']} games (2019),
and tested on {check['test_games']} later games (2020–2023):

| Check | Result |
|---|---|
| Range | estimate ± {check['half_width']:.2f} rating points |
| Test games whose real rating fell inside the range | **{check['coverage']:.1%}** (target {COVERAGE:.0%}) |
| &nbsp;&nbsp;publisher with {KNOWN_PUBLISHER_MIN_GAMES}+ earlier rated games ({check['known_publisher_games']} games) | {check['coverage_known_publisher']:.1%} |
| &nbsp;&nbsp;other publishers ({check['other_publisher_games']} games) | {check['coverage_other_publisher']:.1%} |
| Average error of the estimate | {check['test_mae']:.3f} |

## The model in the app

Built the same way on more recent data: fitted on {len(train)} games (2017–2020) and calibrated on
{len(calib)} games (2021–2023). Its range is estimate ± {q:.2f} rating points. There are no later games
left to test it on, so the check above is the evidence that the method works.

## Limitations

- A range of about ±{q:.1f} points on a 10-point scale is wide. That is an honest reflection of how
  little these inputs reveal about a game's rating (see `EVALUATION.md`).
- The range has the same width for every game, so the {COVERAGE:.0%} holds on average across games,
  not separately for every kind of game (the table shows two groups).
- Coverage is only guaranteed if future games resemble the calibration games.
"""
    with open(os.path.join(ROOT, "analysis", "INTERVALS.md"), "w") as f:
        f.write(report)
    print(report)


if __name__ == "__main__":
    main()
