#!/usr/bin/env python3
"""producer.py — WBS 6.1. Rating-event producer simulator (CONTRACTS.md §5).
MovieLens 32M is a historical dataset (ARCH.txt §3.2: "đây có thể là simulated
event"), so this simulator stands in for the real "USER / APP -> User Rating"
arrow in the architecture.

Modes:
  scenario  - fixed, ordered sequence for a demo user (tier 0 -> few -> enough)
  random    - N random valid events sampled from --movie-ids
  invalid   - deliberately invalid events, one per known failure reason
  duplicate - resend one eventId N times (idempotency test)

acks=all + enable.idempotence=True (producer-side exactly-once per partition);
key = str(userId) so one user's events stay ordered within their partition.

Run:
    python -m streaming.producer --mode scenario --user-id 300001 \
        --movie-ids 296,318,858 --bootstrap-servers localhost:9094
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import uuid
from dataclasses import asdict

from confluent_kafka import Producer

from streaming.schemas import RatingEvent

DEFAULT_TOPIC = "ratings.v1"


def make_producer(bootstrap_servers: str) -> Producer:
    return Producer({
        "bootstrap.servers": bootstrap_servers,
        "acks": "all",
        "enable.idempotence": True,
    })


def _delivery_report(err, msg) -> None:
    if err is not None:
        print(f"  DELIVERY FAILED: {err}")
    else:
        print(f"  delivered -> partition={msg.partition()} offset={msg.offset()}")


def send_event(producer: Producer, topic: str, event: RatingEvent) -> None:
    payload = {
        "eventId": event.event_id,
        "userId": event.user_id,
        "movieId": event.movie_id,
        "rating": event.rating,
        "timestamp": event.timestamp,
        "source": event.source,
    }
    producer.produce(
        topic,
        key=str(event.user_id),
        value=json.dumps(payload).encode("utf-8"),
        callback=_delivery_report,
    )
    producer.poll(0)
    print(f"  produced eventId={event.event_id} userId={event.user_id} movieId={event.movie_id} rating={event.rating}")


def scenario_events(user_id: int, movie_ids: list[int]) -> list[RatingEvent]:
    now = int(time.time())
    return [
        RatingEvent(event_id=str(uuid.uuid4()), user_id=user_id, movie_id=mid,
                    rating=random.choice([3.5, 4.0, 4.5, 5.0]), timestamp=now + i, source="demo")
        for i, mid in enumerate(movie_ids)
    ]


def random_events(n: int, movie_ids: list[int], user_id_range: tuple[int, int]) -> list[RatingEvent]:
    now = int(time.time())
    valid_ratings = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    return [
        RatingEvent(
            event_id=str(uuid.uuid4()),
            user_id=random.randint(*user_id_range),
            movie_id=random.choice(movie_ids),
            rating=random.choice(valid_ratings),
            timestamp=now + i,
            source="simulator",
        )
        for i in range(n)
    ]


def invalid_events(user_id: int, movie_ids: list[int]) -> list[RatingEvent]:
    now = int(time.time())
    return [
        RatingEvent(event_id="", user_id=user_id, movie_id=movie_ids[0], rating=4.0, timestamp=now, source="bad"),
        RatingEvent(event_id=str(uuid.uuid4()), user_id=0, movie_id=movie_ids[0], rating=4.0, timestamp=now, source="bad"),
        RatingEvent(event_id=str(uuid.uuid4()), user_id=user_id, movie_id=999_999_999, rating=4.0, timestamp=now, source="bad"),
        RatingEvent(event_id=str(uuid.uuid4()), user_id=user_id, movie_id=movie_ids[0], rating=7.0, timestamp=now, source="bad"),
        RatingEvent(event_id=str(uuid.uuid4()), user_id=user_id, movie_id=movie_ids[0], rating=4.0, timestamp=0, source="bad"),
        RatingEvent(event_id=str(uuid.uuid4()), user_id=user_id, movie_id=movie_ids[0], rating=4.0,
                    timestamp=now + 999_999_999, source="bad"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=["scenario", "random", "invalid", "duplicate"])
    parser.add_argument("--bootstrap-servers", default="localhost:9094")
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--user-id", type=int, default=300001)
    parser.add_argument("--movie-ids", default="296,318,858", help="comma-separated movieIds")
    parser.add_argument("--n", type=int, default=10, help="event count for --mode random/duplicate")
    parser.add_argument("--event-id", default=None, help="fixed eventId for --mode duplicate")
    args = parser.parse_args()

    movie_ids = [int(x) for x in args.movie_ids.split(",")]
    producer = make_producer(args.bootstrap_servers)

    if args.mode == "scenario":
        events = scenario_events(args.user_id, movie_ids)
    elif args.mode == "random":
        events = random_events(args.n, movie_ids, (1, 200_948))
    elif args.mode == "invalid":
        events = invalid_events(args.user_id, movie_ids)
    else:  # duplicate
        eid = args.event_id or str(uuid.uuid4())
        now = int(time.time())
        events = [
            RatingEvent(event_id=eid, user_id=args.user_id, movie_id=movie_ids[0], rating=4.5, timestamp=now, source="dup")
            for _ in range(args.n)
        ]

    print(f"Producing {len(events)} event(s) to {args.topic} @ {args.bootstrap_servers} (mode={args.mode})")
    for event in events:
        send_event(producer, args.topic, event)

    producer.flush(10)
    print("OK: all events flushed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
