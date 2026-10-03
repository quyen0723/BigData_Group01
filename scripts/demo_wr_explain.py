#!/usr/bin/env python3
"""demo_wr_explain.py — shows, with the system's own numbers, what weighted rating (WR) does to the list a brand-new
user receives (tier 0_history). Read-only: it only reads two JSON files, it does not touch Mongo or the API.

  movielens32m/artifacts/popular_movies.json   the list BEFORE WR (score = plain average rating, support = rating count)
  artifacts/popular_movies.json                the list AFTER WR  (score = WR), the one now loaded in Mongo

WR = v/(v+m)*R + m/(v+m)*C    R = average rating of the movie, v = its number of ratings,
                              C = mean rating of the whole training set (3.5287), m = 1000 ("prior sample size").

Run:  python scripts/demo_wr_explain.py            (m = 1000, as in the system)
      python scripts/demo_wr_explain.py --m 0      (no shrinkage: the order goes back to the plain average)
      python scripts/demo_wr_explain.py --m 5000   (stronger shrinkage)
Only the 10 movies of the old list have an exact average and count in the files; the full computation over the
22.4 million training ratings is Person 1's offline job (src/modeling/split_baselines.py).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "movielens32m" / "artifacts" / "popular_movies.json"
NEW = ROOT / "artifacts" / "popular_movies.json"
C_TRAIN = 3.5287


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["items"]


def wr(v: int, r: float, m: float, c: float) -> float:
    return v / (v + m) * r + m / (v + m) * c


def short(title: str, n: int = 32) -> str:
    return title if len(title) <= n else title[: n - 2] + ".."      # ASCII only: Windows consoles garble "…"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--m", type=float, default=1000.0, help="prior sample size (the system uses 1000)")
    ap.add_argument("--c", type=float, default=C_TRAIN, help="global mean rating of the training set")
    args = ap.parse_args()
    m, c = args.m, args.c

    old, new = load(OLD), load(NEW)
    cutoff = new[-1]["score"]

    print(f"WR = v/(v+m)*R + m/(v+m)*C     m = {m:g}   C = {c}\n")
    print("1) The list BEFORE WR: ranked by plain average rating (only movies with at least 100 ratings)")
    print("   avg-rank  movie                             ratings(v)   avg(R)")
    for x in old:
        print(f"   #{x['rank']:<8} {short(x['title']):32s} {x['support']:>9}   {x['score']:.3f}")

    scored = [(x, wr(x["support"], x["score"], m, c)) for x in old]
    by_wr = sorted(scored, key=lambda t: (-t[1], -t[0]["support"], t[0]["movieId"]))
    wr_rank = {t[0]["movieId"]: i + 1 for i, t in enumerate(by_wr)}

    print("\n2) The same 10 movies after WR: how much each movie is trusted (w = v/(v+m)) and what it scores")
    print("   movie                             v        R      w=v/(v+m)   WR      rank by avg -> rank by WR")
    for x, w_r in scored:
        w = x["support"] / (x["support"] + m) if (x["support"] + m) else 1.0
        print(f"   {short(x['title']):32s} {x['support']:>7}  {x['score']:.3f}   {w*100:5.1f}%     {w_r:.3f}   #{x['rank']:<2} -> #{wr_rank[x['movieId']]}")

    print("\n3) Step by step, two movies")
    for want in ("Planet Earth", "Shawshank"):
        x = next(i for i in old if i["title"].startswith(want))
        v, r = x["support"], x["score"]
        w = v / (v + m)
        print(f"   {x['title']}: v={v}, R={r}")
        print(f"     trust in its own average  w = {v}/({v}+{m:g}) = {w:.3f}   ({w*100:.1f}% own average, {(1-w)*100:.1f}% pulled to the global mean)")
        print(f"     WR = {w:.3f} x {r} + {1-w:.3f} x {c} = {wr(v, r, m, c):.3f}")

    print(f"\n4) The list a NEW user gets now (stored in Mongo, ranked by WR, m=1000): cut-off of the top 10 is WR {cutoff}")
    print("   rank  movie                             WR      ratings(v)")
    for x in new:
        print(f"   #{x['rank']:<4} {short(x['title']):32s} {x['score']:.3f}  {x['support']:>9}")

    old_ids = {x["movieId"] for x in old}
    new_ids = {x["movieId"] for x in new}
    left = [x["title"] for x in old if x["movieId"] not in new_ids]
    came = [x["title"] for x in new if x["movieId"] not in old_ids]
    print(f"\n   left the top 10: {', '.join(short(t, 28) for t in left) or '-'}")
    print(f"   entered the top 10: {', '.join(short(t, 28) for t in came) or '-'}")
    if m != 1000:
        print("\n   (m differs from the system's 1000: sections 1-3 show what-if numbers; section 4 is the stored list)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
