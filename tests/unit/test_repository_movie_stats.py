# Tests: MongoServingRepository.get_movie_stats (the cache, the completeness checks) and the shape of the ledger pipeline.
# The aggregation itself is held to the Python reference against a real Mongo by scripts/check_live_popularity_store.py.
import datetime as dt

import pytest

from serving.config import MongoConfig
from serving.popularity import BaselineStats
from serving.repository import META_KEYS, MongoServingRepository, rating_deltas_pipeline


class FakeColl:
    def __init__(self, docs):
        self.docs = docs
        self.find_calls = 0

    def find_one(self, flt):
        return next((d for d in self.docs if d["_id"] == flt["_id"]), None)

    def find(self, flt, projection=None):
        self.find_calls += 1
        assert flt == {"_id": {"$type": "number"}}                          # the _meta document must never be read as a movie
        return [d for d in self.docs if isinstance(d["_id"], (int, float))]


def repo_with(docs):
    coll = FakeColl(docs)
    repo = MongoServingRepository.__new__(MongoServingRepository)            # no pymongo client: only the two methods under test run
    repo._db = {"movie_stats": coll}
    repo._collections = {"movie_stats": "movie_stats"}
    repo._stats_cache = None
    return repo, coll


def meta(**over):
    base = {"_id": "_meta", "generatedAt": "g1", "movies": 2, "C": 3.5, "cutoff": 1.0, "ratings": 300, "ledgerSince": None}
    base.update(over)
    return base


DOCS = [{"_id": 1, "n0": 100, "sum0": 400.0}, {"_id": 2, "n0": 200, "sum0": 800.0}]


def test_no_meta_means_no_baseline():
    repo, _ = repo_with(list(DOCS))
    assert repo.get_movie_stats() is None


def test_a_complete_baseline_is_read_once_per_generation():
    repo, coll = repo_with([meta(), *DOCS])
    first = repo.get_movie_stats()
    assert isinstance(first, BaselineStats)
    assert first.stats == {1: (100, 400.0), 2: (200, 800.0)} and first.c == 3.5 and first.ratings == 300 and first.ledger_since is None
    assert repo.get_movie_stats() is first and coll.find_calls == 1          # same generatedAt: no second read of the documents


def test_a_rebuilt_baseline_is_picked_up_and_a_removed_one_clears_the_cache():
    repo, coll = repo_with([meta(), *DOCS])
    first = repo.get_movie_stats()
    coll.docs[0] = meta(generatedAt="g2", movies=3)
    coll.docs.append({"_id": 3, "n0": 50, "sum0": 100.0})
    second = repo.get_movie_stats()
    assert second is not first and 3 in second.stats and coll.find_calls == 2
    coll.docs[0] = {"_id": "not-meta"}                                        # the loader removed _meta while it rewrites
    assert repo.get_movie_stats() is None and repo._stats_cache is None


def test_a_partially_loaded_collection_is_refused():
    repo, _ = repo_with([meta(movies=3), *DOCS])
    with pytest.raises(RuntimeError, match="incomplete load"):
        repo.get_movie_stats()


@pytest.mark.parametrize("key", META_KEYS)
def test_a_meta_without_a_required_key_says_which(key):
    broken = meta()
    del broken[key]
    repo, _ = repo_with([broken, *DOCS])
    with pytest.raises(RuntimeError, match=f"missing .*{key}"):
        repo.get_movie_stats()


def test_the_ledger_pipeline_has_the_documented_shape():
    plain = rating_deltas_pipeline(None)
    assert [list(stage)[0] for stage in plain] == ["$sort", "$group", "$group"]
    assert plain[0]["$sort"] == {"timestamp": 1, "ingestedAt": 1, "_id": 1}      # the tie-break order of deltas_from_events
    assert plain[1]["$group"]["_id"] == {"u": "$userId", "m": "$movieId"} and "$last" in plain[1]["$group"]["rating"]
    mark = dt.datetime(2026, 10, 3, 9, 0, 0)
    marked = rating_deltas_pipeline(mark)
    assert marked[0] == {"$match": {"ingestedAt": {"$gt": mark}}} and marked[1:] == plain   # strictly after, before anything is sorted
