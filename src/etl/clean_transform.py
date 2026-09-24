# clean_transform.py — WBS 1.2: Clean, transform, join core datasets.
# Contract: contracts/CONTRACTS.md §1 (constraints) → §2 (curated schemas).
# Gates (PLAN B1.2): no unresolved critical quality issue; joins validated;
# every check emits measured counts (KILL-EDA: no claim without a number).
import sys
from pathlib import Path

import yaml
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from etl.ingest import SCHEMA_LINKS, SCHEMA_MOVIES, SCHEMA_RATINGS, SCHEMA_TAGS

CFG = yaml.safe_load((ROOT / "configs" / "spark.yaml").read_text())

VALID_RATINGS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]  # CONTRACTS §1.1

def main():
    spark = (SparkSession.builder
             .appName("movielens-clean")
             .master(CFG["spark"]["master"])
             .config("spark.driver.memory", CFG["spark"]["driver_memory"])
             .config("spark.sql.shuffle.partitions", CFG["spark"]["sql"]["shuffle_partitions"])
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    raw = ROOT / "data" / "raw" / "ml-32m"

    def read(name, schema):
        from etl.ingest import read_csv
        return read_csv(spark, raw / f"{name}.csv", schema, name)

    ratings = read("ratings", SCHEMA_RATINGS)
    movies = read("movies", SCHEMA_MOVIES)
    tags = read("tags", SCHEMA_TAGS)
    links = read("links", SCHEMA_LINKS)

    report = {}

    # ---- 1) Null checks (per contract: non-nullable columns) ----
    for name, df, cols in [("ratings", ratings, ["userId", "movieId", "rating", "timestamp"]),
                           ("movies", movies, ["movieId", "title", "genres"]),
                           ("tags", tags, ["userId", "movieId", "tag", "timestamp"])]:
        n = df.count()
        nulls = df.filter(" OR ".join(f"{c} IS NULL" for c in cols)).count()
        report[f"null_{name}"] = (n, nulls)
        print(f"[null-check] {name}: rows={n:,}, null-in-key-cols={nulls:,}")

    # ---- 2) Invalid rating check (contract §1.1: rating in VALID_RATINGS) ----
    n_ratings = ratings.count()
    invalid_rating = ratings.filter(
        ~F.col("rating").isin(VALID_RATINGS)).count()
    print(f"[rating-check] ratings rows={n_ratings:,}, invalid-rating={invalid_rating:,}")
    report["invalid_rating"] = (n_ratings, invalid_rating)

    # ---- 3) Duplicate (userId, movieId) in ratings (contract: unique key) ----
    dup_pairs = (ratings.groupBy("userId", "movieId").count()
                 .filter("count > 1").count())
    print(f"[dup-check] duplicate (userId,movieId) groups={dup_pairs:,}")
    report["dup_ratings"] = dup_pairs

    # ---- 4) Timestamp transform: unix epoch -> timestamp + year (contract §2.1) ----
    ratings = (ratings
               .withColumn("rating_ts", F.to_timestamp(F.from_unixtime("timestamp")))
               .withColumn("year", F.year("rating_ts")))
    bad_ts = ratings.filter(F.col("rating_ts").isNull()).count()
    min_ts, max_ts = ratings.agg(F.min("rating_ts"), F.max("rating_ts")).first()
    print(f"[ts-check] converted nulls={bad_ts:,}; range={min_ts} .. {max_ts}")
    report["ts"] = (bad_ts, str(min_ts), str(max_ts))

    # ---- 5) Join ratings + movies by movieId; log unmatched ----
    n_before = ratings.count()
    joined = ratings.join(movies, "movieId", "left")
    unmatched = joined.filter(F.col("title").isNull()).count()
    print(f"[join-check] ratings joined to movies: before={n_before:,}, "
          f"unmatched movieId={unmatched:,}")
    report["join_ratings_movies"] = (n_before, unmatched)

    # movies not present in any rating (informational, not an error)
    rated_movie_ids = ratings.select("movieId").distinct()
    unrated_movies = movies.join(rated_movie_ids, "movieId", "left_anti").count()
    print(f"[join-check] movies with zero ratings={unrated_movies:,}")
    report["unrated_movies"] = unrated_movies

    # ---- 6) movies/links 1:1 check ----    n_movies = movies.count()
    n_links = links.count()
    movie_ids = movies.select("movieId")
    link_unmatched = links.join(movie_ids, "movieId", "left_anti").count()
    print(f"[join-check] links rows={n_links:,}, links without movie={link_unmatched:,}")
    report["links"] = (n_links, link_unmatched)

    # ---- 7) Genre parse: pipe-separated -> genre_list (contract §2.2) ----
    movies = (movies
              .withColumn("genre_list", F.split("genres", "\|"))
              .withColumn("movie_year", F.regexp_extract("title", r"\((\d{4})\)\s*$", 1))
              .withColumn("movie_year", F.col("movie_year").cast("int")))
    no_genre = movies.filter(F.array_contains("genre_list", "(no genres listed)")).count()
    print(f"[genre-check] movies with '(no genres listed)'={no_genre:,}")
    report["no_genre"] = no_genre

    # ---- Apply filters: keep only valid, non-duplicate ratings ----
    clean = (ratings
             .filter(F.col("rating").isin(VALID_RATINGS))
             .dropDuplicates(["userId", "movieId"]))
    n_clean = clean.count()
    print(f"[result] clean ratings: {n_clean:,} (from {n_ratings:,}, "
          f"removed={n_ratings - n_clean:,})")
    report["clean_ratings"] = (n_ratings, n_clean)

    spark.stop()

    # Gate: unresolved CRITICAL issue = nulls>0, invalid>0, dup>0, or unmatched join>0
    critical = (report["null_ratings"][1] + report["null_movies"][1] + report["null_tags"][1]
                + report["invalid_rating"][1] + report["dup_ratings"]
                + report["join_ratings_movies"][1])
    print(f"[gate] critical issues total = {critical:,}")
    print("B1.2 VERIFY:", "PASS" if critical == 0 else "FAIL (see counts above)")
    sys.exit(0 if critical == 0 else 1)

if __name__ == "__main__":
    main()