# split_baselines.py — WBS 3.1 + 3.2 (runs LOCALLY; mirrors Colab notebook 01)
# B3.1: Global Temporal Split 70/15/15 (cutoffs = timestamp quantiles, deterministic)
# B3.2: Movie Mean baseline (RMSE) + Popularity Top-N (min-support grid + deterministic check)
# Gates (PLAN): KILL-LEAKAGE (temporal order), KILL-METRIC (RMSE band [0.6, 1.1]),
#               KILL-CONTRACT (popular_movies.json per CONTRACTS.md 3.1)
# Evidence: evidence/b3_1_split_baseline.txt
# Note: Colab notebook 03 reads evidence/split_stats.csv from Drive — after this run,
#       upload split_stats.csv to Drive movielens32m/evidence/ (see README_COLAB_SETUP).
import sys
import json
import datetime
from pathlib import Path

import yaml
import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.ml.evaluation import RegressionEvaluator

ROOT = Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((ROOT / "configs" / "spark.yaml").read_text())
CURATED = ROOT / CFG["paths"]["curated_dir"]
ARTIFACTS = ROOT / "artifacts"
EVID = ROOT / "evidence" / "b3_1_split_baseline.txt"
ARTIFACTS.mkdir(exist_ok=True)

MIN_SUPPORT_GRID = [50, 100, 500]
MS_FINAL = 100          # default; justification from metrics comparison (INV6)
RMSE_BAND = (0.6, 1.1)  # PLAN research: ALS well-tuned 0.7-0.9; baselines ~0.9-1.05

def main():
    spark = (SparkSession.builder
             .appName("movielens-split")
             .master("local[*]")
             .config("spark.driver.memory", "6g")  # cache 32M x2 -> 6g (spills to disk if short)
             .config("spark.sql.shuffle.partitions", CFG["spark"]["sql"]["shuffle_partitions"])
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    ratings = spark.read.parquet(str(CURATED / "curated_ratings")).cache()
    n_total = ratings.count()
    assert n_total == 32000204, "ERR2: count mismatch vs PRD"

    # ---------- B3.1 split (approxQuantile on epoch long; relativeError 1e-4) ----------
    q = ratings.approxQuantile("timestamp", [0.70, 0.85], 1e-4)
    cut_val, cut_test = q[0], q[1]
    train = ratings.filter(F.col("timestamp") < cut_val).cache()
    val = ratings.filter((F.col("timestamp") >= cut_val) & (F.col("timestamp") < cut_test)).cache()
    test = ratings.filter(F.col("timestamp") >= cut_test).cache()
    n_tr, n_va, n_te = train.count(), val.count(), test.count()

    max_tr = train.agg({"timestamp": "max"}).first()[0]
    min_va = val.agg({"timestamp": "min"}).first()[0]
    min_te = test.agg({"timestamp": "min"}).first()[0]
    leak_free = (max_tr < min_va) and (min_va < min_te)
    assert leak_free, "KILL-LEAKAGE: temporal split leakage — STOP"

    split_stats = pd.DataFrame({
        "n_total": [n_total], "n_train": [n_tr], "n_val": [n_va], "n_test": [n_te],
        "cut_val": [cut_val], "cut_test": [cut_test],
        "method": ["global_temporal_70_15_15"], "leak_free": [leak_free]})
    split_stats.to_csv(ROOT / "evidence" / "split_stats.csv", index=False)
    ratings.unpersist(blocking=True)

    # ---------- B3.2a Movie Mean baseline ----------
    ev = RegressionEvaluator(metricName="rmse", labelCol="rating")
    global_mean = train.agg(F.avg("rating")).first()[0]
    movie_mean = train.groupBy("movieId").agg(F.avg("rating").alias("m_mean"))

    def rmse_movie_mean(df):
        pred = (df.join(movie_mean, "movieId", "left")
                .withColumn("prediction", F.coalesce(F.col("m_mean"), F.lit(global_mean))))
        return ev.evaluate(pred)

    rmse_mm_val = rmse_movie_mean(val)
    rmse_mm_test = rmse_movie_mean(test)
    assert RMSE_BAND[0] <= rmse_mm_test <= RMSE_BAND[1], \
        f"KILL-METRIC: MovieMean RMSE {rmse_mm_test:.4f} outside band {RMSE_BAND}"

    # ---------- B3.2b Popularity Top-N ----------
    pop_stats = (train.groupBy("movieId")
                 .agg(F.count("*").alias("support"), F.avg("rating").alias("avg_rating")))
    movies_meta = spark.read.parquet(str(CURATED / "curated_movies")).select(
        "movieId", "title", "genres")
    results = {}
    for ms in MIN_SUPPORT_GRID:
        top = (pop_stats.filter(F.col("support") >= ms).join(movies_meta, "movieId")
               .orderBy(F.desc("avg_rating"), F.desc("support"), F.asc("movieId")).limit(10))
        results[ms] = [r["movieId"] for r in top.collect()]
    t2 = (pop_stats.filter(F.col("support") >= 100).join(movies_meta, "movieId")
          .orderBy(F.desc("avg_rating"), F.desc("support"), F.asc("movieId")).limit(10))
    deterministic = [r["movieId"] for r in t2.collect()] == results[100]
    assert deterministic, "KILL: popularity not deterministic (tie-break failed)"

    # ---------- artifact per CONTRACTS 3.1 ----------
    pop_rows = (pop_stats.filter(F.col("support") >= MS_FINAL).join(movies_meta, "movieId")
               .withColumn("score", F.col("avg_rating"))
               .orderBy(F.desc("score"), F.desc("support"), F.asc("movieId"))
               .limit(10).collect())
    doc = {"scope": "global", "modelVersion": "v1.0.0",
           "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
           "items": [{"movieId": r["movieId"], "title": r["title"], "genres": r["genres"],
                      "rank": i + 1, "score": round(r["score"], 3), "support": int(r["support"])}
                     for i, r in enumerate(pop_rows)]}
    (ARTIFACTS / "popular_movies.json").write_text(json.dumps(doc, indent=2))
    pd.DataFrame({"model": ["MovieMean"], "rmse_val": [rmse_mm_val],
                  "rmse_test": [rmse_mm_test]}).to_csv(
        ROOT / "evidence" / "metrics_partial.csv", index=False)

    # ---------- evidence ----------
    with EVID.open("w") as out:
        out.write("B3.1 SPLIT + B3.2 BASELINES (local run)\n")
        out.write(f"n_total={n_total:,}\n")
        out.write(f"cut_val={cut_val} cut_test={cut_test}\n")
        out.write(f"train={n_tr:,} ({100*n_tr/n_total:.1f}%) val={n_va:,} "
                  f"({100*n_va/n_total:.1f}%) test={n_te:,} ({100*n_te/n_total:.1f}%)\n")
        out.write(f"KILL-LEAKAGE: max(train)={max_tr} < min(val)={min_va} < min(test)={min_te} : {leak_free} -> PASS\n")
        out.write(f"MovieMean global fallback mean={global_mean:.4f}\n")
        out.write(f"MovieMean RMSE val={rmse_mm_val:.4f} test={rmse_mm_test:.4f} band={RMSE_BAND} -> PASS\n")
        out.write(f"Popularity deterministic (ms=100): {deterministic} -> PASS\n")
        out.write(f"Popularity top5 per min_support: {[(ms, ids[:5]) for ms, ids in results.items()]}\n")
        out.write("popular_movies.json written (contract 3.1)\n")
        out.write("VERIFY: PASS\n")
    print(EVID.read_text())
    spark.stop()
    sys.exit(0)

if __name__ == "__main__":
    main()