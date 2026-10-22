"""PySpark version of prepare_data.py: the same Steam preparation, written for Spark.

It produces the same columns and values as prepare_data.py (checked by
compare_spark_pandas.py), but replaces the per-studio Python loop that builds each
developer's and publisher's track record with Spark window functions, so the work is
spread across cores or a cluster instead of running row by row.

Run from the repository root:
    python3 steam_analysis/prepare_data_spark.py                 # writes data/steam_games_spark.csv
    python3 steam_analysis/prepare_data_spark.py --scale 100     # benchmark on 100 renamed copies

--scale N stacks N copies of the data with renamed store IDs, developers and publishers, so
each copy is an independent set of studios. It is a load test only; its output is not used
by the models.
"""
import argparse
import os
import time

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "steam_analysis", "data", "raw")
OUT_CSV = os.path.join(ROOT, "steam_analysis", "data", "steam_games_spark.csv")

STUDY_YEARS = list(range(2014, 2019))
MIN_REVIEWS = 50
VERY_POSITIVE = 0.80
TRACK_RECORD_LAG_DAYS = 365
SMOOTHING = 3
PRIOR_REACH = 50.0
GAME_GENRES = ["Action", "Adventure", "Casual", "Indie", "RPG", "Simulation", "Strategy", "Sports",
               "Racing", "Massively Multiplayer", "Free to Play", "Early Access"]


def clean_list(col):
    """Split a ';'-separated field and drop empty entries, like split() in prepare_data.py."""
    return F.filter(F.split(F.coalesce(col, F.lit("")), ";"), lambda x: (x != "") & (x != "nan"))


PANDAS_NA_STRINGS = ["", "NaN", "nan", "NA", "N/A", "n/a", "NULL", "null", "None", "<NA>", "#N/A"]


def main_name(col):
    # pandas.read_csv turns these strings into missing values; Spark keeps them as text.
    col = F.when(col.isin(PANDAS_NA_STRINGS), F.lit(None)).otherwise(col)
    parts = clean_list(F.coalesce(col, F.lit("Unknown")))
    return F.when(F.size(parts) > 0, parts[0]).otherwise(F.lit("Unknown"))


def track_record(df, key: str, prior_vp: float):
    """A studio's earlier games released at least TRACK_RECORD_LAG_DAYS before each game:
    how many, their smoothed average reach percentile and Very Positive rate."""
    short = key.replace("_main", "")
    w = (Window.partitionBy(key).orderBy("release_day")
         .rangeBetween(Window.unboundedPreceding, -TRACK_RECORD_LAG_DAYS))
    n = F.count(F.lit(1)).over(w)
    reach_sum = F.sum("reach_percentile").over(w)
    vp_sum = F.sum("very_positive").over(w)
    vp_n = F.count("very_positive").over(w)
    no_date = F.col("release_day").isNull()          # undated games have no earlier games
    n = F.when(no_date, 0).otherwise(n)
    reach_sum = F.when(no_date, 0.0).otherwise(F.coalesce(reach_sum, F.lit(0.0)))
    vp_sum = F.when(no_date, 0.0).otherwise(F.coalesce(vp_sum, F.lit(0.0)))
    vp_n = F.when(no_date, 0).otherwise(vp_n)
    return (df.withColumn(f"{short}_prior_games", n.cast("int"))
              .withColumn(f"{short}_prior_reach",
                          F.bround((reach_sum + PRIOR_REACH * SMOOTHING) / (n + SMOOTHING), 3))
              .withColumn(f"{short}_prior_vp",
                          F.bround((vp_sum + F.lit(prior_vp) * SMOOTHING) / (vp_n + SMOOTHING), 4)))


def load(spark, scale: int):
    games = spark.read.csv(os.path.join(RAW, "steam.csv"), header=True, inferSchema=True,
                           multiLine=True, escape='"')
    desc = spark.read.csv(os.path.join(RAW, "short_descriptions.csv"), header=True, inferSchema=True,
                          multiLine=True, escape='"')
    df = games.join(desc, games.appid == desc.steam_appid, "left").drop("steam_appid")
    if scale > 1:
        copies = spark.range(scale).withColumnRenamed("id", "copy")
        df = (df.crossJoin(copies)
                .withColumn("appid", F.col("appid") + F.col("copy") * 10_000_000)
                .withColumn("developer", F.when(F.col("copy") == 0, F.col("developer"))
                            .otherwise(F.concat(F.coalesce("developer", F.lit("Unknown")), F.lit("#"), F.col("copy"))))
                .withColumn("publisher", F.when(F.col("copy") == 0, F.col("publisher"))
                            .otherwise(F.concat(F.coalesce("publisher", F.lit("Unknown")), F.lit("#"), F.col("copy"))))
                .drop("copy"))
    return df


def prepare(spark, scale: int = 1):
    df = load(spark, scale)
    df = df.withColumn("is_game", F.exists(clean_list(F.col("genres")),
                                           lambda g: g.isin(GAME_GENRES))).filter("is_game")

    df = (df.withColumn("release_date", F.to_date("release_date"))
            .withColumn("release_year", F.year("release_date"))
            .withColumn("release_month", F.month("release_date"))
            .withColumn("release_day", F.datediff("release_date", F.lit("1970-01-01")))
            .withColumn("total_reviews", F.col("positive_ratings") + F.col("negative_ratings"))
            .withColumn("positive_share", F.col("positive_ratings") / F.col("total_reviews"))
            .withColumn("very_positive", F.when(F.col("total_reviews") >= MIN_REVIEWS,
                                                (F.col("positive_share") >= VERY_POSITIVE).cast("double")))
            .withColumn("release_period", F.coalesce(F.date_format("release_date", "yyyy-MM"), F.lit("NaT"))))

    # Percentile of review count among games released the same month, using the average
    # rank for ties (pandas rank(pct=True)).
    by_month = Window.partitionBy("release_period")
    ordered = by_month.orderBy("total_reviews")
    ties = Window.partitionBy("release_period", "total_reviews")
    avg_rank = F.rank().over(ordered) + (F.count(F.lit(1)).over(ties) - 1) / 2.0
    df = df.withColumn("reach_percentile", avg_rank / F.count(F.lit(1)).over(by_month) * 100)

    df = (df.withColumn("developer_main", main_name(F.col("developer")))
            .withColumn("publisher_main", main_name(F.col("publisher")))
            .withColumn("self_published", (F.col("developer_main") == F.col("publisher_main")).cast("int"))
            .withColumn("is_free", (F.col("price") == 0).cast("int"))
            .withColumn("mac", F.col("platforms").contains("mac").cast("int"))
            .withColumn("linux", F.col("platforms").contains("linux").cast("int"))
            .withColumn("age_restricted", (F.col("required_age") > 0).cast("int")))

    prior_vp = df.filter(F.col("release_year") < 2017).agg(F.avg("very_positive")).first()[0]
    for key in ["developer_main", "publisher_main"]:
        df = track_record(df, key, prior_vp)
    return df.withColumn("in_study", F.col("release_year").isin(STUDY_YEARS)).drop("release_day")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=int, default=1)
    args = ap.parse_args()
    spark = (SparkSession.builder.appName("gamepulse-prepare").master("local[*]")
             .config("spark.sql.session.timeZone", "UTC")
             .config("spark.sql.shuffle.partitions", "8").config("spark.driver.memory", "5g").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    start = time.time()
    df = prepare(spark, args.scale)
    if args.scale == 1:
        df.toPandas().to_csv(OUT_CSV, index=False)
        rows = df.count()
    else:
        out = os.path.join(ROOT, "steam_analysis", "data", f"benchmark_x{args.scale}.parquet")
        df.write.mode("overwrite").parquet(out)
        rows = spark.read.parquet(out).count()
    print(f"rows={rows:,} scale={args.scale} seconds={time.time() - start:.1f}")
    spark.stop()


if __name__ == "__main__":
    main()
