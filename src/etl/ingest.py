# ingest.py — WBS 1.1: Read MovieLens 32M CSV with explicit schemas (no inference).
# Contract: contracts/CONTRACTS.md §1 (raw data schemas).
# Gate: row counts match configs/spark.yaml dataset_expectations (ERR2);
#       printed schema must match contract types.
import sys
from pathlib import Path

import yaml
from pyspark.sql import SparkSession
from pyspark.sql.functions import col
from pyspark.sql.types import (DoubleType, IntegerType, LongType,
                                StringType, StructField, StructType)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

CFG = yaml.safe_load((ROOT / "configs" / "spark.yaml").read_text())

# Explicit schemas — CONTRACTS.md §1
SCHEMA_RATINGS = StructType([
    StructField("userId", IntegerType(), nullable=False),
    StructField("movieId", IntegerType(), nullable=False),
    StructField("rating", DoubleType(), nullable=False),
    StructField("timestamp", LongType(), nullable=False),
])
SCHEMA_MOVIES = StructType([
    StructField("movieId", IntegerType(), nullable=False),
    StructField("title", StringType(), nullable=False),
    StructField("genres", StringType(), nullable=False),
])
SCHEMA_TAGS = StructType([
    StructField("userId", IntegerType(), nullable=False),
    StructField("movieId", IntegerType(), nullable=False),
    StructField("tag", StringType(), nullable=False),
    StructField("timestamp", LongType(), nullable=False),
])
SCHEMA_LINKS = StructType([
    StructField("movieId", IntegerType(), nullable=False),
    StructField("imdbId", IntegerType(), nullable=True),
    StructField("tmdbId", IntegerType(), nullable=True),
])

def read_csv(spark, path, schema, name):
    """Explicit schema (no inference). PERMISSIVE + corrupt-record column:
    FAILFAST (Spark 3.5.7) mis-parses valid RFC-4180 escaped quotes in tags
    (diag 2026-09-25: PERMISSIVE parses 2,000,072 rows with 0 malformed).
    Corrupt-column assertion keeps FAILFAST's no-silent-tolerance guarantee."""
    from pyspark.sql import functions as F
    corrupt_col = StructField("_corrupt", StringType(), nullable=True)
    df = (spark.read
          .option("header", True)
          .option("mode", "PERMISSIVE")
          .option("quote", '"')
          .option("escape", '"')   # RFC-4180: "" inside quoted field (tags.csv has
                                   # 244 such records; verified 2026-09-25: 2,000,072
                                   # rows, 0 null keys with this option)
          .option("columnNameOfCorruptRecord", "_corrupt")
          .schema(StructType(list(schema.fields) + [corrupt_col]))
          .csv(str(path)))
    n_corrupt = df.filter(F.col("_corrupt").isNotNull()).count()
    if n_corrupt > 0:
        raise ValueError(f"{name}: {n_corrupt} malformed CSV records — STOP")
    return df.drop("_corrupt")

def main():
    spark = (SparkSession.builder
             .appName(CFG["spark"]["app_name"])
             .master(CFG["spark"]["master"])
             .config("spark.driver.memory", CFG["spark"]["driver_memory"])
             .config("spark.sql.shuffle.partitions", CFG["spark"]["sql"]["shuffle_partitions"])
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")

    raw = ROOT / "data" / "raw" / "ml-32m"
    paths = CFG["paths"]
    exp = CFG["dataset_expectations"]
    tol = exp["tolerance_pct"]

    tables = {
        "ratings": (SCHEMA_RATINGS, "ratings.csv", exp["ratings_rows"]),
        "movies": (SCHEMA_MOVIES, "movies.csv", exp["movies_rows"]),
        "tags": (SCHEMA_TAGS, "tags.csv", exp["tags_rows"]),
        "links": (SCHEMA_LINKS, "links.csv", exp["links_rows"]),
    }

    results = {}
    all_ok = True
    for name, (schema, fname, expected) in tables.items():
        p = raw / fname
        if not p.exists():
            print(f"B1.1 FAIL — missing file: {p}")
            sys.exit(1)
        df = read_csv(spark, p, schema, name)
        n = df.count()
        dev = abs(n - expected) / expected * 100
        ok = dev <= tol
        all_ok &= ok
        results[name] = (df, n, expected, ok)
        print(f"[{name}] rows={n:,} expected={expected:,} dev={dev:.3f}% {'OK' if ok else 'MISMATCH-STOP'}")
        print(f"[{name}] schema:")
        df.printSchema()
        df.show(5, truncate=False)

    # Cross-check user count (FACT: every user >= 20 ratings; PRD users=200,948)
    users = results["ratings"][0].select("userId").distinct().count()
    print(f"[ratings] distinct users={users:,} expected={exp['users']:,} "
          f"{'OK' if users == exp['users'] else 'MISMATCH-STOP'}")
    all_ok &= (users == exp["users"])

    spark.stop()
    print("B1.1 VERIFY:", "PASS" if all_ok else "FAIL")
    sys.exit(0 if all_ok else 1)

if __name__ == "__main__":
    main()