# content_based.py — WBS 3.3 (runs LOCALLY; mirrors Colab notebook 02)
# Genres multi-hot + cosine similarity via numpy block-matrix (87,585^2 = 7.66B cells
# can NOT be materialized — block 2048 x 87,585 float32 ~= 717MB/block, keep top-M only).
# Gates: Pulp Fiction lookup, 200 random movies pass contract checks (CONTRACTS 3.2),
#        no self-reference, score in (0,1], rank 1..M.
# Evidence: evidence/b3_3_content_based.txt
import sys
import json
import random
import datetime
from pathlib import Path

import yaml
import numpy as np
import pandas as pd
from pyspark.sql import SparkSession

ROOT = Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((ROOT / "configs" / "spark.yaml").read_text())
CURATED = ROOT / CFG["paths"]["curated_dir"]
ARTIFACTS = ROOT / "artifacts" / "similar_movies.json"
EVID = ROOT / "evidence" / "b3_3_content_based.txt"
TOP_M = 20
BLOCK = 2048

def main():
    spark = (SparkSession.builder
             .appName("content-based")
             .master("local[*]")
             .config("spark.driver.memory", "4g")
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    movies = spark.read.parquet(str(CURATED / "curated_movies"))
    n_movies = movies.count()

    mrows = movies.select("movieId", "genre_list").toPandas()
    mrows["genre_list"] = mrows["genre_list"].apply(
        lambda g: [x for x in g if x != "(no genres listed)"])
    genres_vocab = sorted({g for lst in mrows["genre_list"] for g in lst})
    g_index = {g: i for i, g in enumerate(genres_vocab)}
    D = len(genres_vocab)

    ids = mrows["movieId"].values
    X = np.zeros((len(mrows), D), dtype=np.float32)
    for r, lst in enumerate(mrows["genre_list"]):
        for g in lst:
            X[r, g_index[g]] = 1.0
    norms = np.linalg.norm(X, axis=1)
    norms[norms == 0] = 1e-9
    Xn = X / norms[:, None]

    similar = {}
    for start in range(0, len(ids), BLOCK):
        end = min(start + BLOCK, len(ids))
        sims = Xn[start:end] @ Xn.T
        for bi in range(end - start):
            gi = start + bi
            sims[bi, gi] = -1.0
            idx = np.argpartition(sims[bi], -TOP_M)[-TOP_M:]
            idx = idx[np.argsort(-sims[bi][idx])]
            row = [(int(ids[j]), round(float(sims[bi][j]), 4), k + 1)
                   for k, j in enumerate(idx) if sims[bi][j] > 0]
            if row:
                similar[int(ids[gi])] = row[:TOP_M]
        del sims

    # ---------- gates ----------
    assert 296 in similar and len(similar[296]) == TOP_M, "KILL: Pulp Fiction lookup incomplete"
    for mid in random.Random(42).sample(list(similar), 200):
        items = similar[mid]
        assert all(m != mid for m, s, r in items), "self-reference"
        assert all(0 < s <= 1 for m, s, r in items), "score out of (0,1]"
        assert all(r == i + 1 for i, (m, s, r) in enumerate(items)), "rank mismatch"
        assert all(items[i][1] >= items[i + 1][1] for i in range(len(items) - 1)), "not sorted"

    version = "v1.0.0"
    gen_at = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    docs = [{"movieId": mid, "modelVersion": version, "generatedAt": gen_at,
             "similar": [{"movieId": m, "score": s, "rank": r} for m, s, r in items]}
            for mid, items in similar.items()]
    ARTIFACTS.parent.mkdir(exist_ok=True)
    ARTIFACTS.write_text(json.dumps(docs))

    n_with_sim = len(similar)
    no_sim = n_movies - n_with_sim
    with EVID.open("w") as out:
        out.write("B3.3 CONTENT-BASED SIMILAR MOVIES (local run)\n")
        out.write(f"movies={n_movies:,} genres_vocab={D}: {genres_vocab}\n")
        out.write(f"with similar list: {n_with_sim:,} | no genre overlap (expected ~7,080 no-genres): {no_sim:,}\n")
        out.write(f"Pulp Fiction (296) top5: {similar[296][:5]}\n")
        out.write("contract sample checks: 200 movies PASS (no self, score in (0,1], rank, sorted)\n")
        out.write(f"similar_movies.json written: {len(docs):,} docs, top-M={TOP_M}\n")
        out.write("VERIFY: PASS\n")
    print(EVID.read_text())
    spark.stop()
    sys.exit(0)

if __name__ == "__main__":
    main()