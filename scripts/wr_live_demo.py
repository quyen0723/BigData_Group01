#!/usr/bin/env python3
"""wr_live_demo.py — drives the live weighted-rating demo (change live-weighted-popularity, design D-11). Standard library only.

  check   compare the baseline-only top 10 of GET /debug/popularity with artifacts/popular_movies.json (Person 1's list)
  plan    for every adjacent pair of the live top 12, how many 5-star ratings the lower movie needs to pass the upper one
  inject  send N ratings for one movie from synthetic users (999200001 and up) through POST /ratings, wait until streaming
          has applied them, and print the table before and after with the rank changes
  spam    the same for a low-support movie that has a high average (default: the one with the fewest ratings among the top 50
          by plain average): WR after 10 and 100 ratings and how many it would take to reach the top 10

Every command takes --api (default http://127.0.0.1:8088) and --dry-run (reads only, sends nothing). Rerunning inject is safe: the eventId of
a rating is uuid5("wr-live-demo:<user>:<movie>"), so an already applied rating is recognised and not sent again.
Clean up afterwards with scripts/purge_demo_ratings.py (synthetic users must not reach a retrain handoff).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API = "http://127.0.0.1:8088"
ARTIFACT = ROOT / "artifacts" / "popular_movies.json"
NAMESPACE = uuid.UUID("6f1c1e0a-2b7d-4c55-9a52-7a1d2f3c4b5e")
USER_START = 999_200_001
USER_LIMIT = 999_999_999            # the purge script refuses ids outside 999,000,000..999,999,999
WR_TOLERANCE = 0.0005 + 1e-9        # the artifact rounds WR to 3 decimals (error up to 0.0005), plus float noise

Http = Callable[[str, str, object], "tuple[int, dict]"]


# ---------------------------------------------------------------- pure helpers (unit-tested)

def wr_after(v: int, total: float, n: int, stars: float, m: float, c: float) -> float:
    """WR of a movie with `v` ratings summing to `total` after `n` more ratings of `stars`."""
    return (total + n * stars + m * c) / (v + n + m)


def ratings_needed(upper_wr: float, v: int, total: float, m: float, c: float, stars: float = 5.0) -> int | None:
    """Smallest n of `stars`-star ratings after which the lower movie's WR is strictly above `upper_wr` (the upper one does not
    move). None when `stars` cannot lift it above that WR."""
    if wr_after(v, total, 0, stars, m, c) > upper_wr:
        return 0
    if stars <= upper_wr:
        return None
    n = int((upper_wr * (v + m) - total - m * c) / (stars - upper_wr)) + 1
    while wr_after(v, total, n, stars, m, c) <= upper_wr:        # guard against float rounding at the boundary
        n += 1
    while n > 0 and wr_after(v, total, n - 1, stars, m, c) > upper_wr:
        n -= 1
    return n


def event_id(user_id: int, movie_id: int) -> str:
    return str(uuid.uuid5(NAMESPACE, f"wr-live-demo:{user_id}:{movie_id}"))


def compare_with_artifact(items: list[dict], artifact: list[dict]) -> list[str]:
    """Problems between the live baseline-only list and Person 1's artifact; empty = identical order and WR within 0.0005."""
    problems = []
    live_ids = [i["movieId"] for i in items[: len(artifact)]]
    art_ids = [a["movieId"] for a in artifact]
    if live_ids != art_ids:
        problems.append(f"order differs: live {live_ids} vs artifact {art_ids}")
    for live, art in zip(items, artifact):
        if live["movieId"] == art["movieId"] and abs(live["wr"] - art["score"]) > WR_TOLERANCE:
            problems.append(f"WR of {art['movieId']} differs by {abs(live['wr'] - art['score']):.5f} ({live['wr']:.4f} vs {art['score']})")
    return problems


def plan_pairs(items: list[dict], m: float, c: float, stars: float = 5.0) -> list[dict]:
    """For each adjacent pair (upper = rank k, lower = rank k+1): how many `stars` ratings the lower one needs to pass."""
    rows = []
    for upper, lower in zip(items, items[1:]):
        total = lower["avgRating"] * lower["support"]
        rows.append({
            "upper": upper, "lower": lower, "gap": upper["wr"] - lower["wr"],
            "needed": ratings_needed(upper["wr"], lower["support"], total, m, c, stars),
        })
    return rows


def short(title: str, n: int = 34) -> str:
    return title if len(title) <= n else title[: n - 2] + ".."


def table(items: list[dict], before: list[dict] | None = None) -> str:
    """The popular list as text. With `before`, each row also shows its rank and WR change."""
    prior = {i["movieId"]: i for i in (before or [])}
    lines = ["rank  movie                               R        v (new)        WR       vs base" + ("   change" if before else "")]
    for i in items:
        r = "-" if i.get("avgRating") is None else f"{i['avgRating']:.4f}"
        v = f"{i['support']:,}" + (f" (+{i['newRatings']})" if i.get("newRatings") else "")
        base = "-" if i.get("baseRank") is None else f"#{i['baseRank']}"
        row = f"#{i['rank']:<4} {short(i['title']):34s} {r:>7} {v:>14} {i['wr']:>9.4f} {base:>9}"
        if before:
            p = prior.get(i["movieId"])
            if p is None:
                row += "   new in the list"
            elif p["rank"] != i["rank"]:
                row += f"   {'up' if p['rank'] > i['rank'] else 'down'} {abs(p['rank'] - i['rank'])} (was #{p['rank']}, WR {p['wr']:.4f})"
            else:
                row += f"   same (WR {p['wr']:.4f})"
        lines.append(row)
    return "\n".join(lines)


# ---------------------------------------------------------------- HTTP

def http_json(api: str) -> Http:
    def call(method: str, path: str, body: object = None) -> tuple[int, dict]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(api + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                return exc.code, json.loads(raw) if raw else {}
            except ValueError:
                return exc.code, {"detail": raw.decode("utf-8", "replace")[:200]}
        except OSError as exc:
            return 0, {"detail": str(exc)}
    return call


def popularity(http: Http, n: int = 12, m: float | None = None, deltas: bool = True) -> dict:
    path = f"/debug/popularity?n={n}" + (f"&m={m:g}" if m is not None else "") + ("" if deltas else "&deltas=false")
    status, body = http("GET", path, None)
    if status != 200:
        raise SystemExit(f"GET {path} -> {status} {body.get('detail', '')} (is api.demo_enabled on and the api restarted with this change?)")
    return body


def poll_seconds(http: Http) -> float:
    """How long the demo pages wait for "applied": the API's own setting (/debug/system demo.ratingPollTimeoutSeconds), 60 if unreadable."""
    status, body = http("GET", "/debug/system", None)
    value = (body.get("demo") or {}).get("ratingPollTimeoutSeconds") if status == 200 else None
    return float(value) if isinstance(value, (int, float)) and value > 0 else 60.0


def applied(http: Http, eid: str) -> bool:
    status, body = http("GET", f"/ratings/{eid}", None)
    return status == 200 and body.get("status") == "applied"


def pick_users(http: Http, movie_id: int, n: int, start: int = USER_START) -> tuple[list[tuple[int, str, bool]], int]:
    """N synthetic users for this movie as (userId, eventId, alreadyApplied). A user whose event is already applied is ours from an
    earlier run and is reused (nothing to send); a user with history from something else is skipped. Returns also how many were skipped."""
    chosen: list[tuple[int, str, bool]] = []
    skipped = 0
    user = start
    while len(chosen) < n:
        if user > USER_LIMIT:
            raise SystemExit("ran out of synthetic user ids")
        eid = event_id(user, movie_id)
        if applied(http, eid):
            chosen.append((user, eid, True))
        else:
            status, body = http("GET", f"/debug/users/{user}", None)
            if status == 200 and body.get("interaction_count", 0) > 0:
                skipped += 1                                   # somebody else's history: do not mix it in
            else:
                chosen.append((user, eid, False))
        user += 1
    return chosen, skipped


def send(http: Http, user: int, movie_id: int, stars: float, eid: str, retries: int = 3) -> tuple[bool, str]:
    for attempt in range(retries + 1):
        status, body = http("POST", "/ratings", {"userId": user, "movieId": movie_id, "rating": stars, "eventId": eid})
        if status == 202:
            return True, ""
        if status in (0, 503) and attempt < retries:
            time.sleep(1.0)                                    # unknown outcome: retry with the SAME eventId
            continue
        return False, f"{status} {body.get('detail', '')}"
    return False, "no answer"


def inject(http: Http, movie_id: int, stars: float, n: int, dry_run: bool, timeout: float | None = None, quiet: bool = False) -> int:
    before = popularity(http, 12)
    say = (lambda *a: None) if quiet else print
    say(f"popular list before ({before['source']}, m={before['m']:g}, {before['appliedEvents']} ledger ratings counted):")
    say(table(before["items"]))
    users, skipped = pick_users(http, movie_id, n)
    fresh = [u for u in users if not u[2]]
    say(f"\nmovie {movie_id}: {n} synthetic users {users[0][0]}..{users[-1][0]} ({len(users) - len(fresh)} already applied from an earlier run, "
        f"{len(fresh)} to send, {skipped} skipped because they have other history)")
    if dry_run:
        for user, eid, done in users[:5]:
            say(f"  would {'skip (applied)' if done else 'send'}: user {user} eventId {eid}")
        if len(users) > 5:
            say(f"  ... and {len(users) - 5} more")
        say("--dry-run: nothing sent")
        return 0
    if not fresh:
        say("all of these ratings already exist; nothing to send")
        return 0

    started = time.time()
    failed = []
    for user, eid, _ in fresh:
        ok, why = send(http, user, movie_id, stars, eid)
        if not ok:
            failed.append((user, why))
    say(f"sent {len(fresh) - len(failed)} ratings in {time.time() - started:.1f} s (202 = accepted by Kafka, not applied yet)")
    if failed:
        say(f"FAILED to send {len(failed)}: e.g. user {failed[0][0]}: {failed[0][1]}")
        return 1

    deadline = time.time() + (timeout if timeout is not None else poll_seconds(http) + 0.2 * n)
    pending = {eid for _, eid, _ in fresh}
    while pending and time.time() < deadline:
        time.sleep(2)
        pending = {eid for eid in pending if not applied(http, eid)}
        say(f"  waiting for streaming: {len(fresh) - len(pending)}/{len(fresh)} applied ({time.time() - started:.0f} s)")
    if pending:
        say(f"TIMEOUT: {len(pending)} ratings are still pending (is the streaming service healthy?)")
        return 1
    applied_after = time.time() - started

    after = before
    for _ in range(10):                                        # the API caches the list for a couple of seconds
        after = popularity(http, 12)
        if after["appliedEvents"] > before["appliedEvents"]:
            break
        time.sleep(1.5)
    say(f"\nall {len(fresh)} applied {applied_after:.0f} s after sending; popular list now ({after['appliedEvents']} ledger ratings counted):")
    say(table(after["items"], before["items"]))
    return 0


# ---------------------------------------------------------------- commands

def cmd_check(http: Http, args) -> int:
    body = popularity(http, 10, deltas=False)
    if body["source"] != "live":
        print("FAIL: the API has no baseline (source=artifact): run `python -m loaders.build_movie_stats` in the spark container")
        return 1
    artifact = json.loads(Path(args.artifact).read_text(encoding="utf-8"))["items"]
    problems = compare_with_artifact(body["items"], artifact)
    print(table(body["items"]))
    print(f"\nbaseline only (m={body['m']:g}, C={body['c']:.4f}) vs {Path(args.artifact).name}: ", end="")
    if problems:
        print("FAIL")
        for p in problems:
            print("  -", p)
        return 1
    print(f"PASS (same {len(artifact)} movies in the same order, WR within 0.0005)")
    return 0


def cmd_plan(http: Http, args) -> int:
    body = popularity(http, 12)
    if body["source"] != "live":
        print("the API serves the artifact list (no live statistics): nothing to plan")
        return 1
    rows = plan_pairs(body["items"], body["m"], body["c"], args.stars)
    print(table(body["items"]))
    print(f"\nratings of {args.stars:g} stars the lower movie needs to pass the one above it (m={body['m']:g}):")
    for r in rows:
        needed = "impossible" if r["needed"] is None else str(r["needed"])
        print(f"  #{r['lower']['rank']} {short(r['lower']['title'], 30):30s} over #{r['upper']['rank']} {short(r['upper']['title'], 30):30s} gap {r['gap']:.4f} -> {needed}")
    possible = [r for r in rows if r["needed"] is not None]
    if possible:
        best = min(possible, key=lambda r: r["needed"])
        print(f"\nclosest pair: #{best['lower']['rank']} {best['lower']['title']} needs about {best['needed']} ratings to pass #{best['upper']['rank']}.")
        print(f"try:  python scripts/wr_live_demo.py inject --movie {best['lower']['movieId']} --n {best['needed'] + 2}")
    return 0


def cmd_inject(http: Http, args) -> int:
    return inject(http, args.movie, args.stars, args.n, args.dry_run, args.timeout)


def cmd_spam(http: Http, args) -> int:
    live = popularity(http, 10)
    if live["source"] != "live":
        print("the API serves the artifact list (no live statistics): nothing to plan")
        return 1
    m, c = live["m"], live["c"]
    cutoff = live["items"][-1]["wr"]
    pool = popularity(http, 50, m=0)["items"]                  # plain-average ranking: where the high-average, low-count movies are
    if args.movie is None:
        target = min(pool, key=lambda i: i["support"])
    else:
        found = [i for i in pool if i["movieId"] == args.movie]
        if not found:
            print(f"movie {args.movie} is not among the top 50 by plain average: pick one that is, or omit --movie")
            return 1
        target = found[0]
    total, v = target["avgRating"] * target["support"], target["support"]
    need = ratings_needed(cutoff, v, total, m, c, 5.0)
    print(f"{target['title']}: average {target['avgRating']:.3f} from {v:,} ratings; WR now {wr_after(v, total, 0, 5.0, m, c):.3f} (m={m:g}, top-10 cut-off WR {cutoff:.3f})")
    for extra in (10, 100):
        print(f"  +{extra:>3} five-star ratings -> WR {wr_after(v, total, extra, 5.0, m, c):.3f}"
              f"{'  (still outside the top 10)' if wr_after(v, total, extra, 5.0, m, c) <= cutoff else '  (in the top 10)'}")
    if need is None:
        print("  five-star ratings cannot lift it above the top-10 cut-off")
    else:
        print(f"  it would take about {need:,} five-star ratings ({need / v:.1f}x its real count) to reach the top 10: WR resists, it is not immune")
    if args.n <= 0:
        return 0
    print()
    rc = inject(http, target["movieId"], 5.0, args.n, args.dry_run, args.timeout)
    if rc == 0 and not args.dry_run:
        # the movie is not in the top 10, so look it up in the plain-average ranking again and apply the formula to what the API now holds
        now = next((i for i in popularity(http, 50, m=0)["items"] if i["movieId"] == target["movieId"]), None)
        if now is not None:
            v_now, total_now = now["support"], now["avgRating"] * now["support"]
            wr_now = wr_after(v_now, total_now, 0, 5.0, m, c)
            rank_now = next((i["rank"] for i in popularity(http, 10)["items"] if i["movieId"] == target["movieId"]), None)
            print(f"\n{target['title']} now: {v_now:,} ratings, average {now['avgRating']:.3f}, WR {wr_now:.3f} "
                  f"({'#' + str(rank_now) + ' in the top 10' if rank_now else 'still outside the top 10'}; top-10 cut-off WR {cutoff:.3f})")
    return rc


def main(argv: list[str] | None = None, http: Http | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default=DEFAULT_API)
    common = argparse.ArgumentParser(add_help=False)               # --api and --dry-run work before or after the command
    common.add_argument("--api", default=argparse.SUPPRESS, help=f"default {DEFAULT_API}")
    common.add_argument("--dry-run", action="store_true", help="read only: list what would be sent, send nothing")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", parents=[common], help="baseline-only top 10 vs Person 1's artifact")
    p.add_argument("--artifact", default=str(ARTIFACT))
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("plan", parents=[common], help="ratings needed for each adjacent pair to swap")
    p.add_argument("--stars", type=float, default=5.0)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("inject", parents=[common], help="send N ratings for one movie from synthetic users")
    p.add_argument("--movie", type=int, required=True)
    p.add_argument("--stars", type=float, default=5.0)
    p.add_argument("--n", type=int, required=True)
    p.add_argument("--timeout", type=float, default=None, help="seconds to wait for streaming (default: the API's rating poll timeout + 0.2 per rating)")
    p.set_defaults(func=cmd_inject)

    p = sub.add_parser("spam", parents=[common], help="what N five-star ratings do to a low-support movie")
    p.add_argument("--movie", type=int, default=None)
    p.add_argument("--n", type=int, default=100, help="ratings to send (0 = only print the plan)")
    p.add_argument("--timeout", type=float, default=None)
    p.set_defaults(func=cmd_spam)

    args = ap.parse_args(argv)
    if getattr(args, "n", 1) < 0 or (args.cmd == "inject" and args.n < 1):
        ap.error("--n must be at least 1" if args.cmd == "inject" else "--n must not be negative")
    if args.cmd == "inject" and args.stars not in {x / 2 for x in range(1, 11)}:
        ap.error("--stars must be a half-star step from 0.5 to 5.0")
    return args.func(http or http_json(args.api), args)


if __name__ == "__main__":
    sys.exit(main())
