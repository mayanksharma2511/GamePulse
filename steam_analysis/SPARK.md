# PySpark data pipeline

`prepare_data_spark.py` is a PySpark version of `prepare_data.py`. It builds the same table of
games, targets and pre-launch features. The developer and publisher track records, which
`prepare_data.py` builds with a Python loop over each studio's games, are computed with Spark window
functions: for each game, a window over the same studio's games released at least 365 days earlier.

## It gives the same result

`compare_spark_pandas.py` compares the two outputs: **26,913 rows × 41 columns identical**
(numbers to within 1e-6). Two details had to match pandas exactly:
- pandas reads the text "NaN" in a developer field as missing, so the Spark version does too.
- pandas rounds halves to even (39.0625 → 39.062), so the Spark version uses `bround`, not `round`.

## Run time

Measured on a 2-core cloud container with 7 GB RAM (Spark in local mode, Java 21, PySpark 4.0.1).
The larger runs stack renamed copies of the data (new store IDs, developers and publishers), so each
copy is an independent set of studios. They are a load test only; the models use the real data.

| Rows | pandas (`benchmark_pandas.py`) | PySpark (`prepare_data_spark.py`) |
|---|---|---|
| 26,913 (real data) | 29.8 s | 16.0 s |
| 269,130 (10 copies) | 217.0 s | 27.7 s (7.8× faster) |
| 2,691,300 (100 copies) | not run | 77.5 s |

The pandas track-record loop grows with the number of studios, while Spark sorts each studio's games
once and works through studios in parallel. On a cluster (for example Databricks or AWS EMR) the same
script runs unchanged apart from the `master` setting.

## Run it

```
pip install pyspark==4.0.1          # needs Java 17 or 21
python3 steam_analysis/prepare_data.py
python3 steam_analysis/prepare_data_spark.py
python3 steam_analysis/compare_spark_pandas.py
python3 steam_analysis/prepare_data_spark.py --scale 100
python3 steam_analysis/benchmark_pandas.py --scale 10
```
