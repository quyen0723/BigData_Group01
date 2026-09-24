# mapreduce_stats.py — WBS 2.2: Classic MapReduce movie-rating statistics
# (mapper + combiner + reducer) cross-checked against Spark groupBy.
# Per tracker: Hadoop streaming may not read Parquet (risk R3) — input is the
# cleaned ratings CSV equivalent exported from curated data.
# Gate (PLAN B2.2): |MR − Spark| within tolerance for every movie.
# Evidence: evidence/b2_2_mapreduce.txt
#
# MapReduce pipeline (same computation as Hadoop streaming, in-process):
#   MAP:    (userId, movieId, rating) -> (movieId, (rating, 1))
#   COMBINE: partial (sum, count) per movie within partition
#   REDUCE: final (sum, count) -> avg per movie
import sys
from collections import defaultdict
from pathlib import Path

import yaml
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

ROOT = Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((ROOT / "configs" / "spark.yaml").read_text())
EVID = ROOT / "evidence" / "b2_2_mapreduce.txt"

def main():
    spark = (SparkSession.builder
             .appName("movielens-mr")
             .master(CFG["spark"]["master"])
             .config("spark.driver.memory", CFG["spark"]["driver_memory"])
             .config("spark.sql.shuffle.partitions", CFG["spark"]["sql"]["shuffle_partitions"])
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    curated = ROOT / CFG["paths"]["curated_dir"]
    ratings = spark.read.parquet(str(curated / "curated_ratings"))

    # ---- Input for MapReduce: cleaned ratings as text (movieId, rating) ----
    # Export once to evidence-free temp dir (NOT committed; reproducible from parquet)
    mr_input_dir = ROOT / "data" / "mr_input"
    (ratings.select("movieId", "rating").write.mode("overwrite")
     .option("sep", ",").csv(str(mr_input_dir)))

    # ---------------- MAP + COMBINE + REDUCE (classic, per partition) ----------------
    # Read back the csv parts as text lines and run the MR pipeline in Python:
    # this mirrors Hadoop streaming (mapper.py / reducer.py scripts, stdin/stdout)
    # while remaining runnable without a Hadoop install on this machine.
    def mapper(line):
        line = line.strip()
        if not line or line.startswith("movieId"):
            return None
        movie_id, rating = line.split(",")
        return (int(movie_id), (float(rating), 1))

    combiner = defaultdict(lambda: (0.0, 0))      # movieId -> (partial_sum, partial_count)
    n_map_out = 0
    parts = sorted(mr_input_dir.glob("part-*.csv"))
    for part in parts:
        with part.open() as f:
            # --- MAP phase ---
            mapped = (mapper(l) for l in f)
            # --- COMBINE phase (per file = per partition) ---
            local = defaultdict(lambda: (0.0, 0))
            for kv in mapped:
                if kv is None:
                    continue
                k, (r, c) = kv
                s, ct = local[k]
                local[k] = (s + r, ct + c)
                n_map_out += 1
            for k, (s, c) in local.items():
                ps, pc = combiner[k]
                combiner[k] = (ps + s, pc + c)
    # --- REDUCE phase ---
    mr_stats = {k: (s / c, c) for k, (s, c) in combiner.items()}
    print(f"MAP output records: {n_map_out:,} (= all ratings)")
    print(f"REDUCE output movies: {len(mr_stats):,}")

    # ---------------- Spark groupBy ground truth ----------------
    spark_stats = {r["movieId"]: (r["avg"], r["cnt"]) for r in
                   ratings.groupBy("movieId")
                   .agg(F.avg("rating").alias("avg"), F.count("*").alias("cnt"))
                   .collect()}

    # ---------------- Cross-check gate ----------------
    max_avg_diff = 0.0
    max_cnt_diff = 0
    n_checked = 0
    mismatches = []
    for k, (mr_avg, mr_cnt) in mr_stats.items():
        s_avg, s_cnt = spark_stats.get(k, (None, 0))
        if s_avg is None:
            mismatches.append((k, "missing in spark"))
            continue
        d_avg = abs(mr_avg - s_avg)
        d_cnt = abs(mr_cnt - s_cnt)
        max_avg_diff = max(max_avg_diff, d_avg)
        max_cnt_diff = max(max_cnt_diff, d_cnt)
        n_checked += 1
        if d_avg > 1e-6 or d_cnt > 0:
            mismatches.append((k, mr_avg, s_avg, mr_cnt, s_cnt))

    # Tolerance (documented in PLAN B2.2): float sum order differs -> avg tolerance 1e-6
    TOL_AVG = 1e-6
    TOL_CNT = 0
    ok = (len(mr_stats) == len(spark_stats) and not mismatches
          and max_avg_diff <= TOL_AVG and max_cnt_diff <= TOL_CNT)

    with EVID.open("w") as out:
        out.write("MAPREDUCE vs SPARK CROSS-CHECK (WBS 2.2)\n")
        out.write(f"map output records: {n_map_out:,}\n")
        out.write(f"MR movies: {len(mr_stats):,} | Spark movies: {len(spark_stats):,}\n")
        out.write(f"max |avg diff| = {max_avg_diff:.10f} (tol {TOL_AVG})\n")
        out.write(f"max |count diff| = {max_cnt_diff} (tol {TOL_CNT})\n")
        out.write(f"mismatches: {len(mismatches)}\n")
        out.write(f"checked movies: {n_checked:,}\n")
        out.write("VERIFY: " + ("PASS" if ok else "FAIL") + "\n")
        out.write("\nTop-5 movies by rating count (MR pipeline result == Spark):\n")
        for k, (a, c) in sorted(mr_stats.items(), key=lambda x: -x[1][1])[:5]:
            out.write(f"  movieId={k} count={c:,} avg={a:.4f} "
                      f"(spark: {spark_stats[k][1]:,}, {spark_stats[k][0]:.4f})\n")
    print(EVID.read_text())
    spark.stop()
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()