"""Time prepare_data.py's pandas logic on N renamed copies of the data (the same load test as
prepare_data_spark.py --scale N), for comparing the two pipelines.

    python3 steam_analysis/benchmark_pandas.py --scale 10
"""
import argparse
import os
import time

import numpy as np
import pandas as pd

import prepare_data as pdp


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=int, default=1)
    args = ap.parse_args()
    start = time.time()
    games = pd.read_csv(os.path.join(pdp.RAW, "steam.csv"))
    desc = pd.read_csv(os.path.join(pdp.RAW, "short_descriptions.csv"))
    base = games.merge(desc, left_on="appid", right_on="steam_appid", how="left").drop(columns="steam_appid")
    parts = []
    for c in range(args.scale):
        p = base.copy()
        if c:
            p["appid"] = p["appid"] + c * 10_000_000
            p["developer"] = p["developer"].fillna("Unknown") + f"#{c}"
            p["publisher"] = p["publisher"].fillna("Unknown") + f"#{c}"
        parts.append(p)
    df = pd.concat(parts, ignore_index=True)
    df = df[df["genres"].map(pdp.split).map(lambda gs: any(g in pdp.GAME_GENRES for g in gs))].copy()
    df["release_date"] = pd.to_datetime(df["release_date"], errors="coerce")
    df["release_year"] = df["release_date"].dt.year
    df["total_reviews"] = df["positive_ratings"] + df["negative_ratings"]
    df["positive_share"] = df["positive_ratings"] / df["total_reviews"]
    df["very_positive"] = np.where(df["total_reviews"] >= pdp.MIN_REVIEWS,
                                   (df["positive_share"] >= pdp.VERY_POSITIVE).astype(float), np.nan)
    df["release_period"] = df["release_date"].dt.to_period("M").astype(str)
    df["reach_percentile"] = df.groupby("release_period")["total_reviews"].rank(pct=True) * 100
    df["developer_main"] = df["developer"].fillna("Unknown").map(lambda s: pdp.split(s)[0] if pdp.split(s) else "Unknown")
    df["publisher_main"] = df["publisher"].fillna("Unknown").map(lambda s: pdp.split(s)[0] if pdp.split(s) else "Unknown")
    prior_vp = float(df.loc[df["release_year"] < 2017, "very_positive"].mean())
    for key in ["developer_main", "publisher_main"]:
        pdp.track_record(df, key, 50.0, prior_vp)
    print(f"rows={len(df):,} scale={args.scale} seconds={time.time() - start:.1f}")


if __name__ == "__main__":
    main()
