#!/usr/bin/env python3
"""demo_e2e.py — WBS 9.1. End-to-end demo script for Session 10.

Chains together everything already verified manually in this session into one
runnable script: a brand-new user moves 0_history -> few_history via a real
Kafka event, an existing warm user demonstrates ALS + fresh-history exclusion,
and (if a model_registry candidate is staged) the promotion gate fail/pass
paths are exercised.

Run from the HOST (needs the stack up: `docker compose -f docker/docker-compose.yml up -d`).
Requires: pymongo, requests (or urllib) in the calling Python — use .venv-serving.

    .venv-serving/Scripts/python demo_e2e.py --user-id 300099 --api http://127.0.0.1:8088
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request

from pymongo import MongoClient


def api_get(base: str, path: str) -> dict:
    with urllib.request.urlopen(f"{base}{path}", timeout=10) as r:
        return json.loads(r.read())


def step(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def run_in_spark(compose_file: str, *args: str) -> None:
    cmd = ["docker", "compose", "-f", compose_file, "exec", "-T", "spark", "python", *args]
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, default=300099, help="a userId with NO existing history")
    parser.add_argument("--api", default="http://127.0.0.1:8088")
    parser.add_argument("--mongo-uri", default="mongodb://localhost:27017")
    parser.add_argument("--db", default="movielens")
    parser.add_argument("--compose-file", default="docker/docker-compose.yml")
    parser.add_argument("--warm-user-id", type=int, default=1, help="an existing user with an ALS doc")
    args = parser.parse_args()

    db = MongoClient(args.mongo_uri)[args.db]

    step(f"1. Journey A - new user {args.user_id}: 0_history")
    if db.user_history.find_one({"userId": args.user_id}):
        print(f"NOTE: userId={args.user_id} already has history - pick a fresh --user-id for a clean demo")
    resp = api_get(args.api, f"/recommendations/{args.user_id}?k=5")
    print(json.dumps(resp, indent=2)[:600])
    assert resp["tier"] == "0_history", f"expected 0_history, got {resp['tier']}"
    print("PASS: tier=0_history, strategy=POPULARITY")

    step("2. Journey A -> B - rate 3 movies via Kafka (real event, real Structured Streaming)")
    run_in_spark(
        args.compose_file, "-m", "streaming.producer", "--mode", "scenario",
        "--user-id", str(args.user_id), "--movie-ids", "296,318,858",
        "--bootstrap-servers", "kafka:9092",
    )
    print("waiting for the streaming pipeline to apply the batch...")
    for _ in range(30):
        if db.user_history.find_one({"userId": args.user_id}):
            break
        time.sleep(2)
    else:
        raise SystemExit("FAIL: user_history did not appear after 60s - is streaming.pipeline running?")

    resp = api_get(args.api, f"/recommendations/{args.user_id}?k=5")
    print(json.dumps(resp, indent=2)[:600])
    assert resp["tier"] == "few_history", f"expected few_history, got {resp['tier']}"
    print("PASS: request-after-rating sees new history immediately, tier=few_history")

    step(f"3. Journey C - warm user {args.warm_user_id}: ALS + fresh-history exclusion")
    resp = api_get(args.api, f"/recommendations/{args.warm_user_id}?k=5")
    top_movie = resp["recommendations"][0]["movieId"]
    print(f"top ALS recommendation before: movieId={top_movie}")
    assert resp["tier"] == "enough_history" and resp["strategy"] == "ALS+CONTENT"

    step(f"4. Rate that exact movie for user {args.warm_user_id} via Kafka, then re-request")
    import uuid

    event = {"eventId": str(uuid.uuid4()), "userId": args.warm_user_id, "movieId": top_movie,
              "rating": 5.0, "timestamp": int(time.time()), "source": "demo"}
    script = (
        "import json,time,uuid; from confluent_kafka import Producer; "
        f"p=Producer({{'bootstrap.servers':'kafka:9092','acks':'all','enable.idempotence':True}}); "
        f"p.produce('ratings.v1', key='{args.warm_user_id}', value=json.dumps({event}).encode()); p.flush(10)"
    )
    run_in_spark(args.compose_file, "-c", script)
    print("waiting for the fresh rating to be applied...")
    for _ in range(30):
        if db.user_rated.find_one({"userId": args.warm_user_id, "movieId": top_movie}):
            break
        time.sleep(2)
    else:
        raise SystemExit("FAIL: fresh rating was not applied after 60s")

    resp = api_get(args.api, f"/recommendations/{args.warm_user_id}?k=5")
    new_ids = [r["movieId"] for r in resp["recommendations"]]
    assert top_movie not in new_ids, f"FAIL: {top_movie} still in recommendations after being rated"
    print(f"PASS: movieId={top_movie} correctly excluded even though the precomputed ALS doc still contains it")

    step("5. Replay the SAME rating event again (idempotency)")
    run_in_spark(args.compose_file, "-c", script)
    time.sleep(6)
    count = db.rating_events.count_documents({"_id": event["eventId"]})
    assert count == 1, f"FAIL: expected exactly 1 ledger doc for the replayed eventId, got {count}"
    print(f"PASS: eventId {event['eventId']} applied exactly once despite being sent twice")

    step("DEMO COMPLETE - all assertions passed")
    print("Not run here (needs a real candidate from Person 1, see design.md D-12):")
    print("  orchestration.retrain_trigger --force")
    print("  orchestration.stage_candidate --version vX.Y.Z --candidate-dir /data/candidates/vX.Y.Z")
    print("  orchestration.promotion_gate --version vX.Y.Z   (fail-path already verified: evidence/p2_6_2_promotion_fail_run_log.txt)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
