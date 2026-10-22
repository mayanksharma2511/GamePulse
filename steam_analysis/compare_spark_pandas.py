"""Check that prepare_data_spark.py reproduces prepare_data.py exactly.

Run both scripts first, then:
    python3 steam_analysis/compare_spark_pandas.py
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "steam_analysis", "data")


def main() -> int:
    pd_df = pd.read_csv(os.path.join(DATA, "steam_games.csv")).sort_values("appid").reset_index(drop=True)
    sp_df = pd.read_csv(os.path.join(DATA, "steam_games_spark.csv")).sort_values("appid").reset_index(drop=True)
    failures = []
    if len(pd_df) != len(sp_df):
        failures.append(f"row count: pandas {len(pd_df)} vs spark {len(sp_df)}")
    if set(pd_df.columns) != set(sp_df.columns):
        failures.append(f"columns differ: {set(pd_df.columns) ^ set(sp_df.columns)}")
    if not (pd_df["appid"].values == sp_df["appid"].values).all():
        failures.append("different games kept")
    checked = 0
    for col in pd_df.columns:
        if col not in sp_df.columns or failures:
            continue
        a, b = pd_df[col], sp_df[col]
        if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
            ok = np.isclose(a.astype(float), b.astype(float), rtol=0, atol=1e-6, equal_nan=True)
        else:
            ok = (a.fillna("<NA>").astype(str).str.replace(r"\.0$", "", regex=True).values
                  == b.fillna("<NA>").astype(str).str.replace(r"\.0$", "", regex=True).values)
        if not ok.all():
            failures.append(f"{col}: {int((~ok).sum())} rows differ")
        checked += 1
    if failures:
        print("MISMATCH"); [print(" -", f) for f in failures]
        return 1
    print(f"MATCH: {len(pd_df):,} rows x {checked} columns identical (numeric tolerance 1e-6)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
