# repository.py — read-side access to the MongoDB serving store (design.md D-3..D-5).
# `ServingRepository` is the interface `service.get_recommendations` depends on; tests use
# an in-memory fake implementing the same interface (no live Mongo needed for unit tests —
# task 4.7's "integration test trên stack thật" is a separate, live-Mongo-only exercise).
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .config import MongoConfig
from .models import HistorySnapshot
from .popularity import BaselineStats
from .timeutil import to_epoch


@dataclass(frozen=True)
class ActivePointer:
    """serving_meta{_id:"active"} — design.md D-5."""
    model_version: str
    artifacts: dict[str, str]   # collection name -> modelVersion serving that collection


class ServingRepository(Protocol):
    def get_active_pointer(self) -> ActivePointer: ...
    def get_user_history(self, user_id: int) -> HistorySnapshot | None: ...
    def get_user_recommendations(self, user_id: int, model_version: str) -> list[dict] | None: ...
    def get_similar_movies(self, movie_ids: list[int], model_version: str) -> dict[int, list[dict]]: ...
    def get_popular_movies(self, model_version: str) -> list[dict]: ...
    def get_rated_movie_ids(self, user_id: int, candidate_ids: frozenset[int]) -> frozenset[int]: ...
    def get_movies(self, movie_ids: frozenset[int]) -> dict[int, dict]: ...
    def movie_exists(self, movie_id: int) -> bool: ...
    def get_rating_event(self, event_id: str) -> dict | None: ...
    def get_pipeline_state(self) -> dict | None: ...
    def get_rating_history(self, user_id: int, limit: int) -> tuple[int, list[dict]]: ...
    def get_demo_movies(self, id_range_start: int, since: datetime) -> list[dict]: ...
    def create_demo_movie(self, title: str, genres: list[str], id_range_start: int, now: datetime) -> dict: ...
    def delete_demo_movie(self, movie_id: int, id_range_start: int) -> bool: ...
    def get_model_registry(self) -> list[dict]: ...
    def get_retrain_progress(self) -> dict: ...
    def get_movie_stats(self) -> BaselineStats | None: ...
    def get_catalog(self) -> list[dict]: ...
    def get_rating_deltas(self, ledger_since: datetime | None) -> dict[int, tuple[int, float]]: ...


META_KEYS = ("generatedAt", "movies", "C", "cutoff", "ratings")      # what movie_stats._meta must carry


def rating_deltas_pipeline(ledger_since: datetime | None) -> list[dict]:
    """Per movie, the (count, sum) of ratings applied by streaming: one rating per (userId, movieId), the latest by
    (timestamp, ingestedAt, _id); with `ledger_since`, only events ingested after it. Kept as a function so its shape is tested
    and so scripts/check_live_popularity_store.py can run exactly this against a real Mongo."""
    pipeline: list[dict] = []
    if ledger_since is not None:
        pipeline.append({"$match": {"ingestedAt": {"$gt": ledger_since}}})
    pipeline += [
        {"$sort": {"timestamp": 1, "ingestedAt": 1, "_id": 1}},
        {"$group": {"_id": {"u": "$userId", "m": "$movieId"}, "rating": {"$last": "$rating"}}},
        {"$group": {"_id": "$_id.m", "n": {"$sum": 1}, "sum": {"$sum": "$rating"}}},
    ]
    return pipeline


class MongoServingRepository:
    """pymongo-backed implementation (design.md D-4 collections, D-5 pointer cache).

    Requires a live MongoDB with the store bootstrapped (specs/serving-store).
    Not exercised by unit tests — covered by the integration test matrix (task 4.7,
    8.1) once Docker + the movielens32m bundle are available.
    """

    def __init__(self, uri: str, cfg: MongoConfig):
        import pymongo  # imported lazily so this module loads without pymongo installed

        self._client = pymongo.MongoClient(uri)
        self._db = self._client[cfg.db]
        self._collections = cfg.collections
        self._pointer_ttl = cfg.serving_meta_cache_ttl_seconds
        self._pointer_cache: ActivePointer | None = None
        self._pointer_cached_at: float = 0.0
        self._stats_cache: BaselineStats | None = None      # movie_stats, loaded once per generatedAt

    def get_active_pointer(self) -> ActivePointer:
        now = time.monotonic()
        if self._pointer_cache is not None and (now - self._pointer_cached_at) < self._pointer_ttl:
            return self._pointer_cache
        doc = self._db[self._collections["serving_meta"]].find_one({"_id": "active"})
        if doc is None:
            raise RuntimeError("serving_meta has no active pointer — has bootstrap load run?")
        pointer = ActivePointer(model_version=doc["modelVersion"], artifacts=dict(doc["artifacts"]))
        self._pointer_cache = pointer
        self._pointer_cached_at = now
        return pointer

    def get_user_history(self, user_id: int) -> HistorySnapshot | None:
        doc = self._db[self._collections["user_history"]].find_one({"userId": user_id})
        if doc is None:
            return None
        # Mongo stores lastUpdated as a BSON Date; pymongo reads it back as a
        # native datetime.datetime. HistorySnapshot.last_updated is epoch seconds
        # (matches src/serving/history.py's pure-Python representation), so convert.
        last_updated_raw = doc.get("lastUpdated")
        last_updated = to_epoch(last_updated_raw) if last_updated_raw else None   # naive == UTC, not host-local
        return HistorySnapshot(
            interaction_count=doc["interaction_count"],
            recent_movie_ids=tuple(doc.get("recent_movieIds", [])),
            positive_movie_ids=tuple(doc.get("positive_movieIds", [])),
            last_updated=last_updated,
        )

    def get_user_recommendations(self, user_id: int, model_version: str) -> list[dict] | None:
        doc = self._db[self._collections["user_recommendations"]].find_one(
            {"userId": user_id, "modelVersion": model_version}
        )
        return doc["recommendations"] if doc else None

    def get_similar_movies(self, movie_ids: list[int], model_version: str) -> dict[int, list[dict]]:
        if not movie_ids:
            return {}
        cursor = self._db[self._collections["similar_movies"]].find(
            {"movieId": {"$in": movie_ids}, "modelVersion": model_version}
        )
        return {doc["movieId"]: doc["similar"] for doc in cursor}

    def get_popular_movies(self, model_version: str) -> list[dict]:
        doc = self._db[self._collections["popular_movies"]].find_one(
            {"scope": "global", "modelVersion": model_version}
        )
        return doc["items"] if doc else []

    def get_rated_movie_ids(self, user_id: int, candidate_ids: frozenset[int]) -> frozenset[int]:
        if not candidate_ids:
            return frozenset()
        cursor = self._db[self._collections["user_rated"]].find(
            {"userId": user_id, "movieId": {"$in": list(candidate_ids)}},
            {"movieId": 1, "_id": 0},
        )
        return frozenset(doc["movieId"] for doc in cursor)

    def get_movies(self, movie_ids: frozenset[int]) -> dict[int, dict]:
        if not movie_ids:
            return {}
        cursor = self._db[self._collections["movies"]].find({"_id": {"$in": list(movie_ids)}})
        return {doc["_id"]: doc for doc in cursor}

    def movie_exists(self, movie_id: int) -> bool:
        doc = self._db[self._collections["movies"]].find_one({"_id": movie_id}, {"_id": 1})
        return doc is not None

    def get_rating_event(self, event_id: str) -> dict | None:
        """rating_events{_id: eventId} — present only after serve_batch has applied
        it (streaming/pipeline.py step 6: ledger insert happens AFTER effects)."""
        return self._db[self._collections["rating_events"]].find_one({"_id": event_id})

    def get_pipeline_state(self) -> dict | None:
        """pipeline_state{_id:"ratings_stream"} — committed by serve_batch step 7
        on every micro-batch, even an empty one, so lastRunAt reflects liveness."""
        return self._db[self._collections["pipeline_state"]].find_one({"_id": "ratings_stream"})

    def get_rating_history(self, user_id: int, limit: int) -> tuple[int, list[dict]]:
        """(total ratings, most recent rated movies newest first). The order and the set come from
        user_history.recent_movieIds — the same list the router uses for seeds, already capped and
        sorted by the pipeline — so no sort over all of user_rated is needed; stars are one `$in`
        on the (userId, movieId) index. A movie missing from `movies` (e.g. a deleted demo movie)
        is still listed, flagged inCatalog=False."""
        snapshot = self.get_user_history(user_id)
        if snapshot is None:
            return 0, []
        ids = list(snapshot.recent_movie_ids)[:limit]
        stars = {
            d["movieId"]: d["rating"]
            for d in self._db[self._collections["user_rated"]].find(
                {"userId": user_id, "movieId": {"$in": ids}}, {"movieId": 1, "rating": 1, "_id": 0}
            )
        }
        movies = self.get_movies(frozenset(ids))
        items = [
            {
                "movieId": mid,
                "rating": stars.get(mid),
                "title": movies.get(mid, {}).get("title", ""),
                "genres": movies.get(mid, {}).get("genres", ""),
                "inCatalog": mid in movies,
            }
            for mid in ids
        ]
        return snapshot.interaction_count, items

    def get_demo_movies(self, id_range_start: int, since: datetime) -> list[dict]:
        """Demo movies live in a reserved id range, so the existing `_id` index serves the query."""
        cursor = self._db[self._collections["movies"]].find(
            {"_id": {"$gte": id_range_start}, "addedAt": {"$gte": since}}
        )
        return list(cursor)

    def create_demo_movie(self, title: str, genres: list[str], id_range_start: int, now: datetime) -> dict:
        """Ids come from a counter that only moves forward. Deriving the next id from the
        movies still present would reuse a deleted movie's id, and ratings given to the old
        movie (kept in user_rated on purpose) would then attach to the new one."""
        import pymongo
        import pymongo.errors

        counter = self._db[self._collections["pipeline_state"]]
        movies = self._db[self._collections["movies"]]
        floor = id_range_start - 1
        for _ in range(5):
            seq = counter.find_one_and_update(
                {"_id": "demo_movie_seq"},
                [{"$set": {"seq": {"$add": [{"$max": [{"$ifNull": ["$seq", floor]}, floor]}, 1]}}}],
                upsert=True,
                return_document=pymongo.ReturnDocument.AFTER,
            )["seq"]
            doc = {"_id": seq, "title": title, "genres": "|".join(genres), "support": 0, "addedAt": now}
            try:
                movies.insert_one(doc)
                return doc
            except pymongo.errors.DuplicateKeyError:
                continue  # that id was inserted by hand; the counter already moved past it
        raise RuntimeError("could not allocate a demo movieId after 5 attempts")

    def delete_demo_movie(self, movie_id: int, id_range_start: int) -> bool:
        if movie_id < id_range_start:
            return False
        result = self._db[self._collections["movies"]].delete_one({"_id": movie_id})
        return result.deleted_count == 1

    def get_model_registry(self) -> list[dict]:
        return list(self._db[self._collections["model_registry"]].find({}, {"modelCard": 0}).sort("_id", 1))

    def get_retrain_progress(self) -> dict:
        """Same query as orchestration/retrain_trigger.py, so the number shown on the
        demo page is the number the real trigger would see."""
        state = self._db[self._collections["pipeline_state"]].find_one({"_id": "retrain_handoff"})
        watermark = state.get("watermark") if state else None
        query = {"ingestedAt": {"$gt": watermark}} if watermark else {}
        pending = self._db[self._collections["rating_events"]].count_documents(query)
        return {"pending": pending, "watermark": watermark}

    def get_catalog(self) -> list[dict]:
        """Every movie as {_id, title, genres, support} for the demo search (catalog.CatalogCache keeps it for 30 s)."""
        return list(self._db[self._collections["movies"]].find({}, {"title": 1, "genres": 1, "support": 1}))

    def get_movie_stats(self) -> BaselineStats | None:
        """Training-split statistics for live popularity (loaders/build_movie_stats.py).

        The `_meta` document is written last and removed first by the loader, so its presence means the
        collection is complete; its `movies` count is checked too. The ~36k documents are read once and kept
        until `_meta.generatedAt` changes, so each call costs one small read. Returns None when there is no
        usable baseline (the caller then serves the artifact)."""
        coll = self._db[self._collections.get("movie_stats", "movie_stats")]
        meta = coll.find_one({"_id": "_meta"})
        if meta is None:
            self._stats_cache = None
            return None
        missing = [k for k in META_KEYS if k not in meta]
        if missing:
            raise RuntimeError(f"movie_stats._meta is incomplete (missing {', '.join(missing)}): rebuild it with loaders.build_movie_stats")
        cached = self._stats_cache
        if cached is not None and cached.generated_at == meta["generatedAt"]:
            return cached
        stats = {
            doc["_id"]: (int(doc["n0"]), float(doc["sum0"]))
            for doc in coll.find({"_id": {"$type": "number"}}, {"n0": 1, "sum0": 1})
        }
        if len(stats) != meta["movies"]:
            raise RuntimeError(f"movie_stats holds {len(stats):,} movies but _meta says {meta['movies']:,}: incomplete load")
        self._stats_cache = BaselineStats(
            stats=stats,
            c=float(meta["C"]),
            cutoff=float(meta["cutoff"]),
            ratings=int(meta["ratings"]),
            movies=int(meta["movies"]),
            generated_at=meta["generatedAt"],
            ledger_since=meta.get("ledgerSince"),
        )
        return self._stats_cache

    def get_rating_deltas(self, ledger_since: datetime | None) -> dict[int, tuple[int, float]]:
        """Ratings applied by streaming, per movie: (count, sum). One rating per (userId, movieId), the latest by
        (timestamp, ingestedAt, _id); with `ledger_since`, only events ingested after it (the baseline already has the
        rest). The same rule as popularity.deltas_from_events, which is the reference the tests hold this to."""
        cursor = self._db[self._collections["rating_events"]].aggregate(rating_deltas_pipeline(ledger_since), allowDiskUse=True)
        return {doc["_id"]: (int(doc["n"]), float(doc["sum"])) for doc in cursor}
