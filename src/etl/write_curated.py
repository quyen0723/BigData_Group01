# write_curated.py — WBS 1.3: Write Curated Parquet + read-back validation.
# Contract: contracts/CONTRACTS.md §2. Gate: read-back schema + counts identical.
# Reuses ingest.read_csv (explicit schema, escape-quote, corrupt assert).
import sys
from pathlib import Path

import yaml
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from etl.ingest import (SCHEMA_LINKS, SCHEMA_MOVIES, SCHEMA_RATINGS, SCHEMA_TAGS,
                        read_csv)

CFG = yaml.safe_load((ROOT / "configs" / "spark.yaml").read_text())
VALID_RATINGS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]

def transform(ratings, movies, tags, links):
    """Apply B1.2-verified cleaning transforms -> curated schemas (§2)."""
    ratings = (ratings
               .filter(F.col("rating").isin(VALID_RATINGS))
               .dropDuplicates(["userId", "movieId"])
               .withColumn("rating_ts", F.to_timestamp(F.from_unixtime("timestamp")))
               .withColumn("year", F.year("rating_ts")))
    movies = (movies
              .withColumn("genre_list", F.split("genres", "\\|"))
              .withColumn("year", F.regexp_extract("title", r"\((\d{4})\)\s*$", 1).cast("int")))
    return ratings, movies, tags, links

def main():
    spark = (SparkSession.builder
             .appName("movielens-curated")
             .master(CFG["spark"]["master"])
             .config("spark.driver.memory", CFG["spark"]["driver_memory"])
             .config("spark.sql.shuffle.partitions", CFG["spark"]["sql"]["shuffle_partitions"])
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")

    raw = ROOT / "data" / "raw" / "ml-32m"
    curated = ROOT / CFG["paths"]["curated_dir"]
    ratings = read_csv(spark, raw / "ratings.csv", SCHEMA_RATINGS, "ratings")
    movies = read_csv(spark, raw / "movies.csv", SCHEMA_MOVIES, "movies")
    tags = read_csv(spark, raw / "tags.csv", SCHEMA_TAGS, "tags")
    links = read_csv(spark, raw / "links.csv", SCHEMA_LINKS, "links")

    ratings, movies, tags, links = transform(ratings, movies, tags, links)

    exp = CFG["dataset_expectations"]
    tables = {
        "curated_ratings": (ratings, exp["ratings_rows"], "year"),   # partition by year (§2.1)
        "curated_movies": (movies, exp["movies_rows"], None),
        "curated_tags": (tags, exp["tags_rows"], None),
        "curated_links": (links, exp["links_rows"], None),
    }

    all_ok = True
    def sig(sdf):
        # Compare (name, dataType) pairs only: Parquet read-back always returns
        # nullable=true, so nullability flags cannot round-trip (verified 2026-09-25).
        # simpleString(): "array<string>" — ignores containsNull/nullable metadata
        # which Parquet cannot round-trip.
        return [(f.name, f.dataType.simpleString()) for f in sdf.schema.fields]

    for name, (df, expected, part_col) in tables.items():
        out = curated / name
        writer = df.write.mode("overwrite")
        if part_col:
            writer = writer.partitionBy(part_col)
        writer.parquet(str(out))

        # ---- Gate: read-back schema + count identical ----
        back = spark.read.parquet(str(out))
        n_before, n_after = df.count(), back.count()
        cmp_df = df.drop(part_col) if part_col else df
        cmp_back = back.drop(part_col) if part_col else back
        schema_same = sig(cmp_df) == sig(cmp_back)
        count_ok = (n_before == n_after == expected)
        ok = schema_same and count_ok
        all_ok &= ok
        print(f"[{name}] written rows={n_before:,} | read-back rows={n_after:,} "
              f"(expected {expected:,}) | schema={'SAME' if schema_same else 'DIFF'} "
              f"{'OK' if ok else 'FAIL'}")
        print(f"[{name}] path={out}")

    spark.stop()
    print("B1.3 VERIFY:", "PASS" if all_ok else "FAIL")
    sys.exit(0 if all_ok else 1)

if __name__ == "__main__":
    main()