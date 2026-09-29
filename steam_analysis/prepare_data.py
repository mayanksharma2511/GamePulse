"""Prepare the Steam dataset for GamePulse v3 and write an audit report.

Input (download from Kaggle: "Steam Store Games (Clean dataset)" by Nik Davis):
    steam_analysis/data/raw/steam.csv
    steam_analysis/data/raw/steam_description_data.csv

Outputs:
    steam_analysis/data/steam_games.csv   - one row per game with targets and pre-launch features
    steam_analysis/DATA_AUDIT.md          - what was found and every decision made

Run from the repository root:
    python3 steam_analysis/prepare_data.py
"""
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "steam_analysis", "data", "raw")
OUT_CSV = os.path.join(ROOT, "steam_analysis", "data", "steam_games.csv")
OUT_MD = os.path.join(ROOT, "steam_analysis", "DATA_AUDIT.md")

STUDY_YEARS = range(2014, 2019)     # 2019 is excluded: the data stops in May 2019
MIN_REVIEWS = 50                    # reviews needed before a review share is meaningful
VERY_POSITIVE = 0.80                # share of positive reviews for "Very Positive"
TRACK_RECORD_LAG_DAYS = 365         # only count a studio's games released at least a year earlier
SMOOTHING = 3                       # pulls studios with few earlier games towards the average

GAME_GENRES = {"Action", "Adventure", "Casual", "Indie", "RPG", "Simulation", "Strategy", "Sports",
               "Racing", "Massively Multiplayer", "Free to Play", "Early Access"}


def split(value: str) -> list:
    return [v for v in str(value).split(";") if v and v != "nan"]


def track_record(df: pd.DataFrame, key: str, prior_reach: float, prior_vp: float) -> pd.DataFrame:
    """For each game, the studio's earlier games released at least TRACK_RECORD_LAG_DAYS
    before it: how many, their average reach percentile, and their Very Positive rate.
    Only earlier games are used, so no game's own outcome (or a later one) leaks in."""
    out = pd.DataFrame(index=df.index, columns=[f"{key}_prior_games", f"{key}_prior_reach", f"{key}_prior_vp"],
                       dtype=float)
    lag = pd.Timedelta(days=TRACK_RECORD_LAG_DAYS)
    for _, g in df.sort_values("release_date").groupby(key, sort=False):
        dates = g["release_date"].values
        reach = g["reach_percentile"].values
        vp = g["very_positive"].values
        for i, (idx, d) in enumerate(zip(g.index, dates)):
            earlier = dates <= (d - lag)
            n = int(earlier.sum())
            r = reach[earlier]
            v = vp[earlier]
            v = v[~np.isnan(v)]
            out.loc[idx, f"{key}_prior_games"] = n
            out.loc[idx, f"{key}_prior_reach"] = (r.sum() + prior_reach * SMOOTHING) / (n + SMOOTHING)
            out.loc[idx, f"{key}_prior_vp"] = (v.sum() + prior_vp * SMOOTHING) / (len(v) + SMOOTHING)
    return out


def main() -> None:
    games = pd.read_csv(os.path.join(RAW, "steam.csv"))
    # The full description file is about 95 MB, too large for the repository, so the
    # short descriptions are saved to a smaller file that is committed instead.
    full_desc = os.path.join(RAW, "steam_description_data.csv")
    short_desc = os.path.join(RAW, "short_descriptions.csv")
    if os.path.exists(full_desc):
        desc = pd.read_csv(full_desc, usecols=["steam_appid", "short_description"])
        desc.to_csv(short_desc, index=False)
    else:
        desc = pd.read_csv(short_desc)
    n_raw = len(games)
    df = games.merge(desc, left_on="appid", right_on="steam_appid", how="left").drop(columns="steam_appid")
    missing_desc = int(df["short_description"].isna().sum())

    # Keep games, not software (video editors, accounting tools, ...)
    genre_lists = df["genres"].map(split)
    df["is_game"] = genre_lists.map(lambda gs: any(g in GAME_GENRES for g in gs))
    n_software = int((~df["is_game"]).sum())
    df = df[df["is_game"]].copy()

    df["release_date"] = pd.to_datetime(df["release_date"], errors="coerce")
    df["release_year"] = df["release_date"].dt.year
    df["release_month"] = df["release_date"].dt.month
    last_date = df["release_date"].max()

    # Targets
    df["total_reviews"] = df["positive_ratings"] + df["negative_ratings"]
    df["positive_share"] = df["positive_ratings"] / df["total_reviews"]
    enough = df["total_reviews"] >= MIN_REVIEWS
    df["very_positive"] = np.where(enough, (df["positive_share"] >= VERY_POSITIVE).astype(float), np.nan)
    # Older games have had longer to collect reviews, so reach is measured against games
    # released in the same month: 90 means more reviews than 90% of that month's games.
    df["release_period"] = df["release_date"].dt.to_period("M").astype(str)
    df["reach_percentile"] = df.groupby("release_period")["total_reviews"].rank(pct=True) * 100

    # Pre-launch features
    df["developer_main"] = df["developer"].fillna("Unknown").map(lambda s: split(s)[0] if split(s) else "Unknown")
    df["publisher_main"] = df["publisher"].fillna("Unknown").map(lambda s: split(s)[0] if split(s) else "Unknown")
    df["self_published"] = (df["developer_main"] == df["publisher_main"]).astype(int)
    df["is_free"] = (df["price"] == 0).astype(int)
    df["mac"] = df["platforms"].str.contains("mac").astype(int)
    df["linux"] = df["platforms"].str.contains("linux").astype(int)
    df["age_restricted"] = (df["required_age"] > 0).astype(int)

    pre_2017 = df["release_year"] < 2017
    prior_reach = 50.0
    prior_vp = float(df.loc[pre_2017, "very_positive"].mean())
    for key in ["developer_main", "publisher_main"]:
        tr = track_record(df, key, prior_reach, prior_vp)
        short = key.replace("_main", "")
        df[f"{short}_prior_games"] = tr[f"{key}_prior_games"].astype(int)
        df[f"{short}_prior_reach"] = tr[f"{key}_prior_reach"].astype(float).round(3)
        df[f"{short}_prior_vp"] = tr[f"{key}_prior_vp"].astype(float).round(4)

    df["in_study"] = df["release_year"].isin(STUDY_YEARS)
    df.to_csv(OUT_CSV, index=False)

    study = df[df["in_study"]]
    rated = study[study["very_positive"].notna()]
    by_year = study.groupby("release_year").agg(
        games=("appid", "size"),
        median_reviews=("total_reviews", "median"),
        with_50_reviews=("very_positive", "count"),
        very_positive_rate=("very_positive", "mean"),
    )
    year_table = "\n".join(
        f"| {int(y)} | {int(r.games):,} | {int(r.median_reviews)} | {int(r.with_50_reviews):,} | {r.very_positive_rate:.1%} |"
        for y, r in by_year.iterrows())

    report = f"""# Steam data audit

Generated by `steam_analysis/prepare_data.py`. Source: "Steam Store Games (Clean dataset)" by
Nik Davis on Kaggle, collected from the Steam store and SteamSpy. The latest release date in the data
is {last_date:%B %Y}, so the data is a snapshot from around then.

## What was kept

| Step | Games |
|---|---|
| In the raw file | {n_raw:,} |
| Removed as software rather than games (no game genre, e.g. video editors) | {n_software:,} |
| Games | {len(df):,} |
| Released 2014–2018 (the study period) | {len(study):,} |
| &nbsp;&nbsp;of which have {MIN_REVIEWS}+ reviews (used for the reception target) | {len(rated):,} |

2019 is left out because the data stops in {last_date:%B %Y}, so 2019 games had only weeks or months to
collect reviews. Every game had a store description ({missing_desc} missing).

## What is predicted

- **Reception:** whether a game is **Very Positive**, meaning at least {VERY_POSITIVE:.0%} of its reviews are
  positive. Only games with {MIN_REVIEWS}+ reviews are used, because a share of a handful of reviews is
  mostly noise. This means the reception model describes games that found at least some audience.
- **Reach:** how many reviews a game collected compared with other games released **in the same month**, as
  a percentile (90 = more reviews than 90% of that month's games). Review counts are a rough stand-in for
  sales, which the data does not include. Raw counts cannot be compared across release dates, because older
  games have had longer to collect reviews (even within a year, a January game had almost a year longer
  than a December game before the snapshot):

| Release year | Games | Median reviews | Games with {MIN_REVIEWS}+ reviews | Very Positive rate |
|---|---|---|---|---|
{year_table}

The Very Positive rate is higher for 2018 partly because of timing: by the snapshot, a 2018 game needed
more early success to reach {MIN_REVIEWS} reviews than an older game did. The test year therefore has a
different mix of games from the training years, which is one reason to check calibration on it.

## Only information known before launch

Everything the models use must be known before a game comes out. Deliberately **left out**:

- review counts, playtime and owner estimates (these are outcomes, not inputs);
- **user tags** (`steamspy_tags`): chosen by players after release, so they can reflect how a game was
  received. They are only used to describe comparable games, never to predict;
- **Steam Trading Cards** and **Steam Workshop**: often added after release, and trading cards in particular
  have been tied to a game's sales;
- the number of achievements, which can change after release;
- **SteamVR Collectibles** (part of the trading-card system);
- the **Early Access** and **Free to Play** genre labels, because a game's status can change after release
  (games leave Early Access, and some games switch to free after weak sales).

**Used:** price (including whether it is free), platforms (Mac, Linux), age restriction, genres (set by the developer),
store categories such as single-player, co-op or controller support, release month, the store description,
and each developer's and publisher's **track record**.

## Track record without leakage

For each game, the developer's and publisher's track record uses only their games released **at least
{TRACK_RECORD_LAG_DAYS} days earlier**: how many there were, their average reach percentile, and their Very
Positive rate. Studios with few earlier games are pulled towards the average. The one-year gap means a
game's own outcome, and the outcomes of other games from the same test year, are never used. Two
limitations remain. Earlier games' outcomes are measured in the {last_date:%Y} snapshot, so for recent games
they include reviews collected after the game in question came out. And price, platforms and store
categories are as listed in the snapshot, which can differ from launch (for example after a permanent
price cut).

## Other checks

- Duplicate store IDs: {int(games['appid'].duplicated().sum())}. Games sharing a name with another: {int(games['name'].duplicated(keep=False).sum())} (different store entries, kept).
- Free games: {df['is_free'].mean():.1%}. Windows-only games: {(df['platforms'] == 'windows').mean():.1%}.
"""
    with open(OUT_MD, "w") as f:
        f.write(report)
    print(report)


if __name__ == "__main__":
    main()
