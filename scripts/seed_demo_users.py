#!/usr/bin/env python3
"""seed_demo_users.py — prepare the pre-existing demo user for use case 8 (and 2, 3, 4).

Ratings go through POST /ratings, so they take the same Kafka -> Structured Streaming
path as any other rating (curated_ratings gets them too). The eventId is derived from
(userId, movieId), so running the script again changes nothing: the pipeline's ledger
already holds those eventIds.

Needs the stack running, `api.demo_enabled` is NOT required. Standard library only:
    python scripts/seed_demo_users.py
    python scripts/seed_demo_users.py --user-id 700009        # a fresh user once 700008 has been rated further
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

SEED_NAMESPACE = uuid.UUID("6f2c1a52-9d0e-4f4b-8a67-1c6f3b7a9e10")


def seed_event_id(user_id: int, movie_id: int) -> str:
    return str(uuid.uuid5(SEED_NAMESPACE, f"{user_id}:{movie_id}"))


def call(api: str, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(api + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://127.0.0.1:8088")
    parser.add_argument("--user-id", type=int, default=700008)
    parser.add_argument("--movie-ids", default="296,318,858", help="comma-separated movieIds (3 Crime/Drama classics)")
    parser.add_argument("--rating", type=float, default=4.5)
    parser.add_argument("--wait", type=int, default=90, help="seconds to wait for the pipeline to apply (0 = don't wait)")
    args = parser.parse_args()

    movie_ids = [int(x) for x in args.movie_ids.split(",")]
    event_ids = {mid: seed_event_id(args.user_id, mid) for mid in movie_ids}

    for mid, event_id in event_ids.items():
        status, body = call(args.api, "POST", "/ratings", {
            "userId": args.user_id, "movieId": mid, "rating": args.rating, "eventId": event_id,
        })
        print(f"POST /ratings user={args.user_id} movie={mid} -> {status} {body}")
        if status != 202:
            print("FAIL: the API did not accept the rating (is the stack up? is Kafka healthy?)")
            return 1

    if args.wait <= 0:
        print("Not waiting for the pipeline. Check GET /ratings/{eventId} later.")
        return 0

    pending = dict(event_ids)
    deadline = time.monotonic() + args.wait
    while pending and time.monotonic() < deadline:
        for mid, event_id in list(pending.items()):
            _, body = call(args.api, "GET", f"/ratings/{event_id}")
            if body.get("status") == "applied":
                print(f"  applied: movie {mid} (batch {body.get('batchId')})")
                del pending[mid]
        if pending:
            time.sleep(3)

    if pending:
        print(f"TIMEOUT: still pending after {args.wait}s: movies {sorted(pending)} — is streaming.pipeline running?")
        return 2
    print(f"OK: user {args.user_id} seeded with {len(event_ids)} ratings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
