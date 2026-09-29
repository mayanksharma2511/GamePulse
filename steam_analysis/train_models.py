"""Train the models used by the Launch Planner and check them on unseen games.

1. Reception: logistic regression on store info, track record and description (the best
   reception model in EVALUATION.md). Its probabilities are recalibrated on a later year,
   because the share of Very Positive games changes over time.
2. Reach: gradient boosting on store info and track record (the best reach model), with an
   80% range from split conformal prediction.
3. Comparable games: nearest store descriptions (TF-IDF, cosine similarity) among games with
   50+ reviews.

Each method is first checked the way it will be used: fitted on 2014-2016, recalibrated or
calibrated on 2017, and tested on 2018. The app's models are then built the same way on
more recent data (fitted on 2014-2017, calibrated on 2018).

Outputs: ml_engine/steam_models.joblib, steam_analysis/MODELS.md, steam_analysis/model_checks.csv

Run from the repository root (after prepare_data.py):
    python3 steam_analysis/train_models.py
"""
import os
import sys

import joblib
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.metrics.pairwise import linear_kernel
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evaluate import calibration_error, top_share  # noqa: E402
from features import split, tabular, vocabulary  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "steam_analysis", "data", "steam_games.csv")
MODEL_OUT = os.path.join(ROOT, "ml_engine", "steam_models.joblib")
OUT = os.path.join(ROOT, "steam_analysis")
COVERAGE = 0.80
SEED = 0
SMOOTHING = 3


# ---------- Reception ----------

def make_vectorizer():
    return TfidfVectorizer(stop_words="english", min_df=5, max_df=0.5, sublinear_tf=True, max_features=20000)


def fit_reception(train: pd.DataFrame):
    vocab = vocabulary(train)
    X = tabular(train, vocab, True)
    scaler = StandardScaler().fit(X)
    vec = make_vectorizer().fit(train["short_description"].fillna(""))
    M = sparse.hstack([sparse.csr_matrix(scaler.transform(X)),
                       vec.transform(train["short_description"].fillna(""))]).tocsr()
    clf = LogisticRegression(C=0.1, max_iter=3000).fit(M, train["very_positive"].astype(int))
    # Average effect of the description over the training games, so the app can show whether a
    # description pushes the estimate above or below that of an average game.
    text_coef = clf.coef_[0, X.shape[1]:]
    text_mean = float(np.mean(M[:, X.shape[1]:] @ text_coef))
    return {"vocab": vocab, "columns": list(X.columns), "scaler": scaler, "vectorizer": vec, "model": clf,
            "recalibration": (1.0, 0.0), "text_mean": text_mean}


def reception_logit(r, df: pd.DataFrame) -> np.ndarray:
    X = tabular(df, r["vocab"], True)[r["columns"]]
    M = sparse.hstack([sparse.csr_matrix(r["scaler"].transform(X)),
                       r["vectorizer"].transform(df["short_description"].fillna(""))]).tocsr()
    return r["model"].decision_function(M)


def reception_prob(r, df: pd.DataFrame) -> np.ndarray:
    a, b = r["recalibration"]
    return 1 / (1 + np.exp(-(a * reception_logit(r, df) + b)))


def recalibrate(r, calib: pd.DataFrame):
    """Platt scaling: fit a one-feature logistic regression from the model's score to the
    outcome on a later year, so probabilities match that year's rate of Very Positive games."""
    z = reception_logit(r, calib).reshape(-1, 1)
    lr = LogisticRegression(C=1e6, max_iter=1000).fit(z, calib["very_positive"].astype(int))
    r["recalibration"] = (float(lr.coef_[0, 0]), float(lr.intercept_[0]))
    return r


# ---------- Reach ----------

def fit_reach(train: pd.DataFrame):
    vocab = vocabulary(train)
    X = tabular(train, vocab, True)
    model = HistGradientBoostingRegressor(max_depth=4, max_iter=300, learning_rate=0.05, random_state=SEED)
    model.fit(X, train["reach_percentile"])
    return {"vocab": vocab, "columns": list(X.columns), "model": model, "half_width": None}


def reach_pred(m, df: pd.DataFrame) -> np.ndarray:
    return np.clip(m["model"].predict(tabular(df, m["vocab"], True)[m["columns"]]), 0, 100)


def conformal(m, calib: pd.DataFrame):
    errors = np.abs(calib["reach_percentile"].values - reach_pred(m, calib))
    n = len(errors)
    m["half_width"] = float(np.quantile(errors, min(1.0, np.ceil((n + 1) * COVERAGE) / n), method="higher"))
    return m


# ---------- Comparable games ----------

def build_comparables(games: pd.DataFrame):
    vec = make_vectorizer().fit(games["short_description"].fillna(""))
    matrix = vec.transform(games["short_description"].fillna(""))
    cols = ["appid", "name", "release_year", "price", "positive_share", "total_reviews", "owners",
            "steamspy_tags", "genres", "very_positive", "reach_percentile"]
    return {"vectorizer": vec, "matrix": matrix, "games": games[cols].reset_index(drop=True)}


def neighbours(comp, texts, k=10):
    sims = linear_kernel(comp["vectorizer"].transform(texts), comp["matrix"])
    idx = np.argsort(-sims, axis=1, kind="stable")[:, :k]
    return idx, np.take_along_axis(sims, idx, axis=1)


# ---------- Studio track records for new games ----------

def studio_records(df: pd.DataFrame, prior_vp: float) -> dict:
    """Each studio's record as of the end of the data, for games that have not been released yet."""
    records = {}
    for key, name in [("developer_main", "developer"), ("publisher_main", "publisher")]:
        g = df.groupby(key).agg(games=("appid", "size"), reach=("reach_percentile", "sum"),
                                vp_sum=("very_positive", "sum"), vp_n=("very_positive", "count"))
        records[name] = {
            s: {"games": int(r.games),
                "reach": float((r.reach + 50 * SMOOTHING) / (r.games + SMOOTHING)),
                "vp": float((r.vp_sum + prior_vp * SMOOTHING) / (r.vp_n + SMOOTHING))}
            for s, r in g.iterrows() if s != "Unknown"}
    records["default"] = {"games": 0, "reach": 50.0, "vp": prior_vp}
    return records


def main() -> None:
    df = pd.read_csv(DATA, parse_dates=["release_date"])
    study = df[df["in_study"]]
    rated = study[study["very_positive"].notna()]
    checks = {}

    # 1. Reception: fit 2014-2016, recalibrate on 2017, test on 2018
    r = fit_reception(rated[rated["release_year"] <= 2016])
    test = rated[rated["release_year"] == 2018]
    y = test["very_positive"].values.astype(int)
    p_raw = reception_prob(r, test)
    r = recalibrate(r, rated[rated["release_year"] == 2017])
    p_cal = reception_prob(r, test)
    checks.update({
        "reception_test_games": len(test), "reception_test_rate": round(float(y.mean()), 3),
        "reception_auc": round(roc_auc_score(y, p_cal), 3),
        "reception_top20": round(top_share(y, p_cal), 3),
        "reception_brier_before": round(brier_score_loss(y, p_raw), 4),
        "reception_brier_after": round(brier_score_loss(y, p_cal), 4),
        "reception_calibration_error_before": round(calibration_error(y, p_raw), 3),
        "reception_calibration_error_after": round(calibration_error(y, p_cal), 3),
        "reception_mean_prob_before": round(float(p_raw.mean()), 3),
        "reception_mean_prob_after": round(float(p_cal.mean()), 3),
    })

    # 2. Reach: fit 2014-2016, calibrate on 2017, test on 2018
    m = conformal(fit_reach(study[study["release_year"] <= 2016]), study[study["release_year"] == 2017])
    test_r = study[study["release_year"] == 2018]
    err = np.abs(test_r["reach_percentile"].values - reach_pred(m, test_r))
    checks.update({
        "reach_test_games": len(test_r), "reach_half_width": round(m["half_width"], 2),
        "reach_coverage": round(float((err <= m["half_width"]).mean()), 3),
        "reach_mae": round(float(err.mean()), 2),
    })

    # 3. Comparables: for 2018 games, search games released up to 2017
    pool = df[(df["total_reviews"] >= 50) & (df["release_year"] <= 2017)]
    comp = build_comparables(pool)
    idx, _ = neighbours(comp, test["short_description"].fillna(""), k=10)
    test_genres = test["genres"].map(lambda v: set(split(v)) - {"Indie", "Early Access", "Free to Play"})
    pool_genres = comp["games"]["genres"].map(lambda v: set(split(v)) - {"Indie", "Early Access", "Free to Play"})
    shared = np.mean([[len(tg & pool_genres.iloc[j]) > 0 for j in row] for tg, row in zip(test_genres, idx)])
    rng = np.random.default_rng(SEED)
    rand_idx = rng.integers(0, len(pool), size=idx.shape)
    shared_random = np.mean([[len(tg & pool_genres.iloc[j]) > 0 for j in row]
                             for tg, row in zip(test_genres, rand_idx)])
    neighbour_vp = comp["games"]["very_positive"].values[idx].mean(axis=1)
    checks.update({
        "comparables_pool": len(pool),
        "comparables_share_genre": round(float(shared), 3),
        "comparables_share_genre_random": round(float(shared_random), 3),
        "comparables_vp_auc": round(roc_auc_score(y, neighbour_vp), 3),
    })
    pd.DataFrame([checks]).to_csv(os.path.join(OUT, "model_checks.csv"), index=False)

    # App models: the same methods on more recent data
    prior_vp = float(rated.loc[rated["release_year"] <= 2017, "very_positive"].mean())
    app_rec = recalibrate(fit_reception(rated[rated["release_year"] <= 2017]), rated[rated["release_year"] == 2018])
    app_reach = conformal(fit_reach(study[study["release_year"] <= 2017]), study[study["release_year"] == 2018])
    app_comp = build_comparables(df[df["total_reviews"] >= 50])
    ref = study[study["release_year"] == 2017]
    reach_reference = [
        {"percentile": q, "reviews": int(ref.loc[(ref["reach_percentile"] - q).abs() <= 2.5, "total_reviews"].median())}
        for q in range(5, 100, 5)]
    joblib.dump({
        "reach_reference": reach_reference,
        # Share of Very Positive games among 2014-2018 releases with 50+ reviews (a typical game)
        "typical_very_positive": float(rated["very_positive"].mean()),
        "reception": app_rec, "reach": app_reach, "comparables": app_comp,
        "studios": studio_records(df, prior_vp),
        "checks": checks, "coverage": COVERAGE,
        "trained_on": "Steam games released 2014-2017, calibrated on 2018",
        "genre_options": app_rec["vocab"]["genres"],
        "category_options": app_rec["vocab"]["categories"],
    }, MODEL_OUT, compress=3)

    c = checks
    report = f"""# Launch Planner models

Generated by `steam_analysis/train_models.py`. Each method is checked the way the app uses it: fitted on
games released 2014–2016, recalibrated or calibrated on 2017, and tested on 2018. The app's models are
then built the same way on more recent data (fitted on 2014–2017, calibrated on 2018).

## Reception: chance of Very Positive reviews

Logistic regression on store info, track record and the store description. The share of Very Positive
games rose over time, so the probabilities are recalibrated on the most recent year (Platt scaling).

| Check on {c['reception_test_games']:,} games from 2018 | Before recalibration | After |
|---|---|---|
| Average predicted probability (real rate {c['reception_test_rate']:.1%}) | {c['reception_mean_prob_before']:.1%} | {c['reception_mean_prob_after']:.1%} |
| Calibration error | {c['reception_calibration_error_before']:.3f} | {c['reception_calibration_error_after']:.3f} |
| Brier score | {c['reception_brier_before']:.4f} | {c['reception_brier_after']:.4f} |

Ranking is unchanged by recalibration: AUC {c['reception_auc']:.3f}, and {c['reception_top20']:.1%} of the games the
model rated in its top 20% were Very Positive.

## Reach: percentile among games released the same month

Gradient boosting on store info and track record, with an {COVERAGE:.0%} range from split conformal prediction.

| Check on {c['reach_test_games']:,} games from 2018 | Result |
|---|---|
| Range | estimate ± {c['reach_half_width']:.1f} percentile points |
| Games whose real reach fell inside the range | **{c['reach_coverage']:.1%}** (target {COVERAGE:.0%}) |
| Mean absolute error | {c['reach_mae']:.2f} |

Coverage is a little below the target: the 2018 games were harder to place than the 2017 games used to set
the range, which is the risk whenever the market changes between calibration and use.

## Comparable games

The closest store descriptions (TF-IDF, cosine similarity) among {c['comparables_pool']:,} games with 50+ reviews
released up to 2017, checked on the 2018 games:

| Check | Result |
|---|---|
| Top-10 matches sharing at least one genre with the game (excluding Indie) | {c['comparables_share_genre']:.1%} |
| Same, for 10 random games | {c['comparables_share_genre_random']:.1%} |
| AUC of "share of the 10 matches that were Very Positive" as a predictor | {c['comparables_vp_auc']:.3f} |

Matches share a genre with the game more often than random games do, but their reviews alone predict
reception only weakly, which is why the reception estimate comes from the model rather than from the matches.

## Limitations

- The data ends in May 2019; the models describe the Steam market of 2014–2018.
- Reach is measured by review count, a rough stand-in for sales.
- The reception model only covers games that reached 50+ reviews.
- The reach range has the same width for every game, so the {COVERAGE:.0%} holds on average.
"""
    with open(os.path.join(OUT, "MODELS.md"), "w") as f:
        f.write(report)
    print(report)
    print("Model file:", os.path.getsize(MODEL_OUT) / 1e6, "MB")


if __name__ == "__main__":
    main()
