"""Pre-launch features shared by the evaluation, the final models and the app.

Only information a publisher has before release is used (see DATA_AUDIT.md).
"""
import numpy as np
import pandas as pd

# Often added or changed after release (see DATA_AUDIT.md)
EXCLUDED_CATEGORIES = {"Steam Trading Cards", "Steam Workshop", "SteamVR Collectibles"}
EXCLUDED_GENRES = {"Early Access", "Free to Play"}
SOFTWARE_GENRES = {"Utilities", "Design & Illustration", "Animation & Modeling", "Education",
                   "Video Production", "Software Training", "Audio Production", "Web Publishing",
                   "Game Development", "Photo Editing", "Accounting", "Documentary", "Tutorial"}

BASIC_NUMERIC = ["price", "is_free", "mac", "linux", "age_restricted", "english"]
TRACK_RECORD = ["developer_prior_games_log", "developer_prior_reach", "developer_prior_vp",
                "publisher_prior_games_log", "publisher_prior_reach", "publisher_prior_vp", "self_published"]


def split(value) -> list:
    return [v for v in str(value).split(";") if v and v != "nan"]


def vocabulary(train: pd.DataFrame) -> dict:
    """Genres and categories seen in the training games (fixed before looking at test games)."""
    genres = sorted({g for v in train["genres"] for g in split(v)} - SOFTWARE_GENRES - EXCLUDED_GENRES)
    cats = sorted({c for v in train["categories"] for c in split(v)} - EXCLUDED_CATEGORIES)
    return {"genres": genres, "categories": cats}


def tabular(df: pd.DataFrame, vocab: dict, track_record: bool = True) -> pd.DataFrame:
    X = pd.DataFrame(index=df.index)
    for c in BASIC_NUMERIC:
        X[c] = df[c].astype(float)
    X["log_price"] = np.log1p(df["price"].astype(float))
    for m in range(1, 13):
        X[f"month_{m}"] = (df["release_month"] == m).astype(float)
    genre_sets = df["genres"].map(lambda v: set(split(v)))
    for g in vocab["genres"]:
        X[f"genre: {g}"] = genre_sets.map(lambda s: g in s).astype(float)
    cat_sets = df["categories"].map(lambda v: set(split(v)))
    for c in vocab["categories"]:
        X[f"category: {c}"] = cat_sets.map(lambda s: c in s).astype(float)
    if track_record:
        X["developer_prior_games_log"] = np.log1p(df["developer_prior_games"])
        X["publisher_prior_games_log"] = np.log1p(df["publisher_prior_games"])
        for c in ["developer_prior_reach", "developer_prior_vp", "publisher_prior_reach",
                  "publisher_prior_vp", "self_published"]:
            X[c] = df[c].astype(float)
    return X
