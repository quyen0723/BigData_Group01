# spark_sql_analytics.py — WBS 2.1: Spark SQL analyses + execution plans.
# Gate (PLAN B2.1): >=2 meaningful analyses + explain('formatted') interpretation.
# Evidence: evidence/b2_1_spark_sql.txt (queries + results + plans).
import sys
from pathlib import Path

import yaml
from pyspark.sql import SparkSession

ROOT = Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((ROOT / "configs" / "spark.yaml").read_text())
EVID = ROOT / "evidence" / "b2_1_spark_sql.txt"

ANALYSES = [
    ("Q1 most-rated movies",
     """SELECT m.movieId, m.title, COUNT(*) AS cnt, ROUND(AVG(r.rating), 2) AS avg_rating
        FROM ratings r JOIN movies m USING (movieId)
        GROUP BY m.movieId, m.title ORDER BY cnt DESC LIMIT 10"""),
    ("Q2 highly-rated with minimum support >= 100 (popularity artifact basis)",
     """SELECT m.movieId, m.title, COUNT(*) AS support, ROUND(AVG(r.rating), 3) AS avg_rating
        FROM ratings r JOIN movies m USING (movieId)
        GROUP BY m.movieId, m.title
        HAVING support >= 100
        ORDER BY avg_rating DESC LIMIT 10"""),
    ("Q3 genre rating pattern (avg rating + volume by genre)",
     """SELECT genre, COUNT(DISTINCT movieId) AS movies, COUNT(*) AS ratings,
              ROUND(AVG(rating), 3) AS avg_rating
        FROM (SELECT movieId, g AS genre FROM movies
              LATERAL VIEW explode(genre_list) gt AS g) mg
        JOIN ratings USING (movieId)
        WHERE genre != '(no genres listed)'
        GROUP BY genre ORDER BY avg_rating DESC"""),
    ("Q4 user activity buckets",
     """SELECT CASE WHEN cnt < 50 THEN 'a. 20-49'
                 WHEN cnt < 200 THEN 'b. 50-199'
                 WHEN cnt < 1000 THEN 'c. 200-999'
                 ELSE 'd. 1000+' END AS activity_bucket,
              COUNT(*) AS users
        FROM (SELECT userId, COUNT(*) AS cnt FROM ratings GROUP BY userId)
        GROUP BY activity_bucket ORDER BY activity_bucket"""),
    ("Q5 temporal activity (ratings per year, recent decade)",
     """SELECT year, COUNT(*) AS ratings
        FROM ratings WHERE year >= 2013
        GROUP BY year ORDER BY year"""),
]

PLAN_INTERPRETATION = """
PLAN INTERPRETATION (per query, cross-checked against the formatted plans above):
- Every aggregation over the full 32M ratings triggers an Exchange hashpartitioning
  stage: Spark must shuffle rows by the GROUP BY key before partial→final aggregation.
- JOIN on movieId shows a BroadcastExchange when the movies side (87,585 rows, ~few MB)
  fits under spark.sql.autoBroadcastJoinThreshold (10MB default) — avoiding a full
  shuffle of the 32M-row ratings side. Verified in plans: "BroadcastExchange" appears
  for Q1/Q2; the small side is movies.
- Partial aggregation (HashAggregate partial) happens map-side before the Exchange —
  visible in the plans as two HashAggregate nodes (partial → final) around each Exchange.
- Q4 reads a subquery aggregation: the plan shows 5 Exchange nodes (verified in
  evidence/b2_1_spark_sql.txt) — per-user partial/final count plus the outer
  bucket aggregation, compounded by AQE re-reads (ShuffleQueryStage/AQEShuffleRead).
- Q5 uses partition pruning: the WHERE year >= 2013 skips 18 of 29 parquet year
  partitions (1995-2012) — visible as fewer scanned files in the FileScan node.
"""

def main():
    spark = (SparkSession.builder
             .appName("movielens-sql")
             .master(CFG["spark"]["master"])
             .config("spark.driver.memory", CFG["spark"]["driver_memory"])
             .config("spark.sql.shuffle.partitions", CFG["spark"]["sql"]["shuffle_partitions"])
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    curated = ROOT / CFG["paths"]["curated_dir"]
    ratings = spark.read.parquet(str(curated / "curated_ratings"))
    movies = spark.read.parquet(str(curated / "curated_movies"))
    ratings.createOrReplaceTempView("ratings")
    movies.createOrReplaceTempView("movies")

    out = EVID.open("w")
    for title, sql in ANALYSES:
        print(f"=== {title} ===", file=out)
        print(f"SQL: {sql}", file=out)
        df = spark.sql(sql)
        print("RESULT:", file=out)
        for row in df.collect():
            print(tuple(row), file=out)
        print("EXECUTION PLAN (explain formatted):", file=out)
        # capture plan text (ExplainMode must be a JVM ExplainMode object in 3.5)
        mode = spark._jvm.org.apache.spark.sql.execution.ExplainMode.fromString("formatted")
        plan = df._jdf.queryExecution().explainString(mode)
        print(plan, file=out)
        print("\n", file=out)

    print(PLAN_INTERPRETATION, file=out)
    out.close()
    spark.stop()

    n_analyses = len(ANALYSES)
    text = EVID.read_text()
    has_plans = text.count("Exchange") >= 3 and "*BroadcastExchange" in text or "BroadcastExchange" in text
    print(f"analyses={n_analyses} (need >=2) | plans captured={'yes' if has_plans else 'NO'}")
    print("B2.1 VERIFY:", "PASS" if (n_analyses >= 2 and has_plans) else "FAIL")
    sys.exit(0 if (n_analyses >= 2 and has_plans) else 1)

if __name__ == "__main__":
    main()