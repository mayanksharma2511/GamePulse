"""Evaluate how well pre-launch information predicts a Steam game's reception and reach.

Time-based split: models learn from games released 2014-2017 and are tested on games
released in 2018. Model settings are fixed in advance, not tuned on the test games.

Outputs: steam_analysis/results_reception.csv, steam_analysis/results_reach.csv,
         steam_analysis/EVALUATION.md

Run from the repository root (after prepare_data.py):
    python3 steam_analysis/evaluate.py
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from features import tabular, vocabulary  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "steam_analysis", "data", "steam_games.csv")
OUT = os.path.join(ROOT, "steam_analysis")
TEST_YEAR = 2018
N_BOOTSTRAP = 1000
SEED = 0


def text_features(train_text, test_text):
    vec = TfidfVectorizer(stop_words="english", min_df=5, max_df=0.5, sublinear_tf=True, max_features=20000)
    return vec.fit_transform(train_text.fillna("")), vec.transform(test_text.fillna(""))


def with_text(Xtr, Xte, Ttr, Tte):
    scaler = StandardScaler().fit(Xtr)
    return (sparse.hstack([sparse.csr_matrix(scaler.transform(Xtr)), Ttr]).tocsr(),
            sparse.hstack([sparse.csr_matrix(scaler.transform(Xte)), Tte]).tocsr())


def scaled(Xtr, Xte):
    scaler = StandardScaler().fit(Xtr)
    return scaler.transform(Xtr), scaler.transform(Xte)


def top_share(y, p, frac=0.2):
    """Share of the games ranked in the top `frac` by the model that were actually positive.
    Undefined for a constant prediction, which does not rank games at all."""
    if np.ptp(p) == 0:
        return np.nan
    k = int(len(p) * frac)
    return float(np.mean(y[np.argsort(-p, kind="stable")[:k]]))


def calibration_error(y, p, bins=10):
    """Average gap between predicted probability and observed rate, over ten equal-size groups."""
    if np.ptp(p) == 0:
        return float(abs(p[0] - y.mean()))
    order = np.argsort(p, kind="stable")
    groups = np.array_split(order, bins)
    return float(np.mean([abs(p[g].mean() - y[g].mean()) for g in groups]))


def bootstrap_diff(metric, y, p, p_base, rng):
    """95% paired bootstrap interval for metric(model) - metric(baseline)."""
    n, diffs = len(y), []
    for _ in range(N_BOOTSTRAP):
        i = rng.integers(0, n, n)
        if metric is roc_auc_score and len(np.unique(y[i])) < 2:
            continue
        diffs.append(metric(y[i], p[i]) - metric(y[i], p_base[i]))
    return np.percentile(diffs, [2.5, 97.5])


def evaluate_reception(df, rng):
    data = df[df["in_study"] & df["very_positive"].notna()]
    train, test = data[data["release_year"] < TEST_YEAR], data[data["release_year"] == TEST_YEAR]
    y_tr, y_te = train["very_positive"].values.astype(int), test["very_positive"].values.astype(int)
    vocab = vocabulary(train)
    Ttr, Tte = text_features(train["short_description"], test["short_description"])

    preds = {"Base rate (share of Very Positive games in training)": np.full(len(test), y_tr.mean())}
    for label, tr_flag in [("store info", False), ("store info + track record", True)]:
        Xtr, Xte = tabular(train, vocab, tr_flag), tabular(test, vocab, tr_flag)
        a, b = scaled(Xtr, Xte)
        lr = LogisticRegression(C=0.1, max_iter=2000).fit(a, y_tr)
        preds[f"Logistic regression: {label}"] = lr.predict_proba(b)[:, 1]
        hgb = HistGradientBoostingClassifier(max_depth=4, max_iter=300, learning_rate=0.05, random_state=SEED)
        preds[f"Gradient boosting: {label}"] = hgb.fit(Xtr, y_tr).predict_proba(Xte)[:, 1]
    Xtr, Xte = tabular(train, vocab, True), tabular(test, vocab, True)
    a, b = with_text(Xtr, Xte, Ttr, Tte)
    lr = LogisticRegression(C=0.1, max_iter=3000).fit(a, y_tr)
    preds["Logistic regression: store info + track record + description"] = lr.predict_proba(b)[:, 1]

    base = preds["Base rate (share of Very Positive games in training)"]
    rows = []
    for name, p in preds.items():
        auc = roc_auc_score(y_te, p) if np.ptp(p) > 0 else 0.5
        d_lo, d_hi = (np.nan, np.nan) if p is base else bootstrap_diff(brier_score_loss, y_te, p, base, rng)
        rows.append({"method": name, "auc": round(auc, 3), "brier": round(brier_score_loss(y_te, p), 4),
                     "brier_vs_base_low": round(d_lo, 4), "brier_vs_base_high": round(d_hi, 4),
                     "top20_hit_rate": round(top_share(y_te, p), 3),
                     "calibration_error": round(calibration_error(y_te, p), 3)})
    info = {"train": len(train), "test": len(test), "train_rate": y_tr.mean(), "test_rate": y_te.mean()}
    return pd.DataFrame(rows), info


def evaluate_reach(df, rng):
    data = df[df["in_study"]]
    train, test = data[data["release_year"] < TEST_YEAR], data[data["release_year"] == TEST_YEAR]
    y_tr, y_te = train["reach_percentile"].values, test["reach_percentile"].values
    vocab = vocabulary(train)
    Ttr, Tte = text_features(train["short_description"], test["short_description"])

    preds = {"Middle of the month (50th percentile)": np.full(len(test), 50.0)}
    for label, tr_flag in [("store info", False), ("store info + track record", True)]:
        Xtr, Xte = tabular(train, vocab, tr_flag), tabular(test, vocab, tr_flag)
        a, b = scaled(Xtr, Xte)
        preds[f"Ridge regression: {label}"] = Ridge(alpha=10.0).fit(a, y_tr).predict(b)
        hgb = HistGradientBoostingRegressor(max_depth=4, max_iter=300, learning_rate=0.05, random_state=SEED)
        preds[f"Gradient boosting: {label}"] = hgb.fit(Xtr, y_tr).predict(Xte)
    Xtr, Xte = tabular(train, vocab, True), tabular(test, vocab, True)
    a, b = with_text(Xtr, Xte, Ttr, Tte)
    preds["Ridge regression: store info + track record + description"] = Ridge(alpha=30.0).fit(a, y_tr).predict(b)

    base = preds["Middle of the month (50th percentile)"]
    mae = lambda y, p: float(np.mean(np.abs(y - p)))  # noqa: E731
    rows = []
    for name, p in preds.items():
        p = np.clip(p, 0, 100)
        lo, hi = (np.nan, np.nan) if name.startswith("Middle") else bootstrap_diff(mae, y_te, p, base, rng)
        rho = spearmanr(p, y_te)[0] if np.ptp(p) > 0 else np.nan
        rows.append({"method": name, "mae": round(mae(y_te, p), 2),
                     "mae_vs_base_low": round(lo, 2), "mae_vs_base_high": round(hi, 2),
                     "spearman_rho": None if np.isnan(rho) else round(rho, 3)})
    info = {"train": len(train), "test": len(test)}
    return pd.DataFrame(rows), info


def main() -> None:
    df = pd.read_csv(DATA, parse_dates=["release_date"])
    rng = np.random.default_rng(SEED)
    rec, rec_info = evaluate_reception(df, rng)
    reach, reach_info = evaluate_reach(df, rng)
    rec.to_csv(os.path.join(OUT, "results_reception.csv"), index=False)
    reach.to_csv(os.path.join(OUT, "results_reach.csv"), index=False)
    def fmt(x, digits):
        return "—" if pd.isna(x) else f"{x:+.{digits}f}"

    rec_rows = "\n".join(
        f"| {r.method} | {r.auc:.3f} | {'—' if pd.isna(r.top20_hit_rate) else f'{r.top20_hit_rate:.1%}'} | {r.brier:.4f} | "
        f"{'—' if pd.isna(r.brier_vs_base_low) else f'{fmt(r.brier_vs_base_low, 4)} to {fmt(r.brier_vs_base_high, 4)}'} | "
        f"{r.calibration_error:.3f} |" for r in rec.itertuples())
    reach_rows = "\n".join(
        f"| {r.method} | {r.mae:.2f} | "
        f"{'—' if pd.isna(r.mae_vs_base_low) else f'{fmt(r.mae_vs_base_low, 2)} to {fmt(r.mae_vs_base_high, 2)}'} | "
        f"{'—' if pd.isna(r.spearman_rho) else f'{r.spearman_rho:.3f}'} |" for r in reach.itertuples())

    report = f"""# Evaluation: predicting reception and reach before launch

Generated by `steam_analysis/evaluate.py` from `steam_analysis/data/steam_games.csv`.

Models learn from games released 2014–2017 and are tested on games released in {TEST_YEAR}. Settings are
fixed in advance, and only pre-launch information is used (see `DATA_AUDIT.md`). Intervals are 95% paired
bootstrap intervals over the test games; an interval that excludes 0 means the model is clearly better or
worse than the baseline.

## Reception: will the game be Very Positive (80%+ positive reviews)?

Games with 50+ reviews: {rec_info['train']:,} for training, {rec_info['test']:,} for testing.
{rec_info['train_rate']:.1%} of training games and {rec_info['test_rate']:.1%} of test games were Very Positive.

| Method | AUC | Very Positive among the model's top 20% | Brier score | Brier vs. base rate (95% interval) | Calibration error |
|---|---|---|---|---|---|
{rec_rows}

- **AUC:** the chance that the model ranks a random Very Positive game above a random other game
  (0.5 = no better than chance, 1 = perfect).
- **Top 20%:** of the games the model rated most likely, the share that really were Very Positive.
- **Brier score:** average squared error of the probabilities (lower is better).
- **Calibration error:** average gap between predicted probabilities and what happened, over ten groups.
  Part of it comes from the change in the Very Positive rate between the training and test years.

## Reach: where will the game rank by number of reviews?

Reach is a percentile among games released the same month (see `DATA_AUDIT.md`).
{reach_info['train']:,} games for training, {reach_info['test']:,} for testing.

| Method | Mean absolute error (percentile points) | Error vs. baseline (95% interval) | Spearman ρ |
|---|---|---|---|
{reach_rows}
"""
    with open(os.path.join(OUT, "EVALUATION.md"), "w") as f:
        f.write(report)
    print(report)


if __name__ == "__main__":
    main()
