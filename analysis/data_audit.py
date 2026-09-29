"""Audit analysis/finalData.csv and write a cleaned copy for evaluation.

Outputs:
    analysis/clean_games.csv  - the original rows plus audit columns
    analysis/DATA_AUDIT.md    - a short report of what was found

Run from the repository root:
    python3 analysis/data_audit.py
"""
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "analysis", "finalData.csv")
OUT_DIR = os.path.join(ROOT, "analysis")

# Every genre in the dataset mapped to one of 14 broader groups.
# Written out in full so the grouping can be checked and changed.
GENRE_GROUPS = {
    "Action": ["Action", "Hack and slash", "Beat 'em up", "Arcade", "Arcade, Action", "Stealth",
               "Run and gun", "Side-scroller", "Endless runner", "Vehicular combat", "Aerial combat",
               "Bullet hell", "Roguelike"],
    "Action-adventure": ["Action-adventure"],
    "Adventure & story": ["Adventure", "Visual novel", "FMV adventure", "Point-and-click adventure",
                          "Point-and-click Adventure", "Graphic adventure", "Interactive story",
                          "Interactive fiction", "Exploration", "Dating sim", "Puzzle adventure"],
    "Role-playing": ["Role-playing", "Action role-playing", "Tactical role-playing", "Japanese role-playing",
                     "Massively multiplayer online role-playing", "Massively multiplayer online",
                     "Dungeon crawler"],
    "Platformer": ["Platformer", "Platform", "Metroidvania", "Puzzle platformer", "Puzzle-platformer",
                   "Puzzle-platform", "Action platformer"],
    "Puzzle & card": ["Puzzle", "Board game", "Card game", "Collectible card game", "Card battle",
                      "Programming game", "Pinball"],
    "Shooter": ["First-person shooter", "Third-person shooter", "Shoot 'em up", "Twin-stick shooter",
                "Tactical shooter", "Rail shooter", "Top-down shooter", "Shooter", "2D shooter",
                "Hero shooter", "Loot shooter", "Shooting gallery", "Battle royale", "First-person"],
    "Strategy & tactics": ["Turn-based strategy", "Real-time strategy", "Strategy", "Tower defense",
                           "Turn-based tactics", "Real-time tactics", "Multiplayer online battle arena",
                           "Roguelike deck-building"],
    "Simulation & management": ["Simulation", "Business simulation", "Life simulation", "Life simulator",
                                "Construction and management simulation", "City building",
                                "City-building game", "Space flight simulation", "Space flight simulator",
                                "Sandbox", "Sporting management simulation"],
    "Sports & racing": ["Sports", "Racing", "Kart racing", "Exergaming"],
    "Fighting": ["Fighting"],
    "Horror & survival": ["Survival horror", "Survival", "Horror", "Psychological horror"],
    "Music & party": ["Rhythm", "Party", "Music", "Game show", "Social deduction"],
    "Other": ["Compilation", "Indie"],
}
GENRE_TO_GROUP = {g: group for group, genres in GENRE_GROUPS.items() for g in genres}


def has_more_than_two_decimals(x: float) -> bool:
    """True for values like 23.586207; False for 17.99 or 8.5."""
    return abs(round(x, 2) - x) > 1e-6


def parse_year(text) -> float:
    """Pull a four-digit year out of text such as 'Q3 2022' or 'June 2022'."""
    match = re.search(r"(19|20)\d{2}", str(text))
    return float(match.group(0)) if match else float("nan")


def main() -> None:
    df = pd.read_csv(SRC).drop(columns=["Unnamed: 0"], errors="ignore")
    n = len(df)

    # Release dates: full dates where possible, otherwise just the year
    df["release_date"] = pd.to_datetime(df["Released Date"], format="%B %d, %Y", errors="coerce")
    df["release_year"] = df["release_date"].dt.year
    df["release_month"] = df["release_date"].dt.month
    year_only = df["release_date"].isna()
    df.loc[year_only, "release_year"] = df.loc[year_only, "Released Date"].map(parse_year)
    no_full_date = int(year_only.sum())
    no_year = int(df["release_year"].isna().sum())
    tba = int(df["Released Date"].astype(str).str.upper().str.startswith("TBA").sum())

    # Values that are unlikely to be original data. Store prices and review scores
    # are normally given to at most two decimal places; values with more decimals
    # (e.g. 23.586207) match averages, so they were most likely filled in.
    df["price_imputed"] = df["Price"].map(has_more_than_two_decimals)
    df["rating_imputed"] = df["Rating"].map(has_more_than_two_decimals)
    price_mean = df["Price"].mean()
    rating_mean = df["Rating"].mean()
    price_is_global_mean = int((df["Price"] - price_mean).abs().lt(1e-4).sum())
    rating_is_global_mean = int((df["Rating"] - rating_mean).abs().lt(1e-4).sum())

    # Publisher averages: a filled-in rating often equals its publisher's average
    pub_mean = df.groupby("Publisher")["Rating"].transform("mean")
    rating_is_publisher_mean = int((df["rating_imputed"] & (df["Rating"] - pub_mean).abs().lt(1e-3)).sum())

    # Genre groups
    df["genre_group"] = df["Genre"].map(GENRE_TO_GROUP).fillna("Other")
    unmapped = sorted(set(df["Genre"]) - set(GENRE_TO_GROUP))
    small_genres = int((df["Genre"].value_counts() < 5).sum())

    # Rows usable for evaluating predictions: original rating and a known year
    df["usable_for_evaluation"] = ~df["rating_imputed"] & df["release_year"].notna()
    usable = int(df["usable_for_evaluation"].sum())

    df.to_csv(os.path.join(OUT_DIR, "clean_games.csv"), index=False)

    group_counts = df["genre_group"].value_counts()
    group_table = "\n".join(f"| {g} | {c} |" for g, c in group_counts.items())

    report = f"""# Data audit: `analysis/finalData.csv`

Generated by `analysis/data_audit.py`. All numbers below are computed from the data.

## Summary

| Check | Result |
|---|---|
| Games | {n:,} |
| Distinct genres | {df['Genre'].nunique()} ({small_genres} of them have fewer than 5 games) |
| Missing publisher | {int(df['Publisher'].isna().sum())} |
| Release date not a full date | {no_full_date} (of which {tba} are "TBA") |
| No release year at all | {no_year} |
| Ratings with more than two decimals (likely filled in) | {int(df['rating_imputed'].sum())} ({df['rating_imputed'].mean():.0%}) |
| &nbsp;&nbsp;of which equal to the overall average rating ({rating_mean:.4f}) | {rating_is_global_mean} |
| &nbsp;&nbsp;of which equal to their publisher's average rating | {rating_is_publisher_mean} |
| Prices with more than two decimals (likely filled in) | {int(df['price_imputed'].sum())} ({df['price_imputed'].mean():.0%}) |
| &nbsp;&nbsp;of which equal to the overall average price (${price_mean:.4f}) | {price_is_global_mean} |
| Rows usable for evaluation (original rating and a known year) | {usable:,} |

## What this means

- **Ratings are the target.** About {df['rating_imputed'].mean():.0%} of ratings appear to be filled in
  with an average (the overall average or the publisher's average) rather than being real scores.
  A model evaluated on those rows would be scored partly against averages, not real outcomes, so
  evaluation in `analysis/evaluate.py` uses only the {usable:,} rows with an original rating.
- **Prices.** About {df['price_imputed'].mean():.0%} of prices appear to be filled in. These rows are
  kept, but flagged with `price_imputed` so a model can account for them.
- **Genres.** The {df['Genre'].nunique()} genres are grouped into {df['genre_group'].nunique()} broader
  groups (mapping in `GENRE_GROUPS` in this script). Many original genres have too few games to
  give a reliable average on their own.
- **Assumption.** The "more than two decimals" rule is an inference, not a label in the data.
  A real score could occasionally have more decimals, so these counts are estimates.

## Genre groups

| Group | Games |
|---|---|
{group_table}

Unmapped genres (placed in "Other"): {', '.join(unmapped) if unmapped else 'none'}.

## Columns added in `clean_games.csv`

`release_date`, `release_year`, `release_month`, `price_imputed`, `rating_imputed`,
`genre_group`, `usable_for_evaluation`.
"""
    with open(os.path.join(OUT_DIR, "DATA_AUDIT.md"), "w") as f:
        f.write(report)
    print(report)


if __name__ == "__main__":
    main()
