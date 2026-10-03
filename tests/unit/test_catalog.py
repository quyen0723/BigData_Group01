# Tests: openspec/changes/movie-catalog-search/specs/movie-catalog — the pure search, the statistics on each row, the cache.
import math
import random
import threading
import time

import pytest

import serving.catalog as catalog_module
from serving.catalog import MAX_ORDERS, CatalogCache, OrderCache, StatsUnavailable, make_entry, search, tokens
from serving.popularity import weighted_rating

M, C = 1000.0, 3.5


def entry(movie_id, title, genres="Drama", support=0, demo_start=9_000_000):
    return make_entry({"_id": movie_id, "title": title, "genres": genres, "support": support}, demo_start)


CATALOG = [
    entry(296, "Pulp Fiction (1994)", "Comedy|Crime|Drama|Thriller", 98_409),
    entry(59114, "Pulp (1972)", "Comedy|Crime|Thriller", 4_000),
    entry(165863, "Marvel: 75 Years, From Pulp to Pop! (2014)", "Documentary", 300),
    entry(858, "Godfather, The (1972)", "Crime|Drama", 60_000),
    entry(1221, "Godfather: Part II, The (1974)", "Crime|Drama", 40_000),
    entry(2023, "Godfather: Part III, The (1990)", "Crime|Drama|Thriller", 25_000),
    entry(318, "Shawshank Redemption, The (1994)", "Crime|Drama", 102_929),
    entry(3000, "Man from Laramie, The (1955)", "Western", 2_000),
    entry(3001, "Shane (1953)", "Western", 3_000),
    entry(900001, "Brand New (2019)", "Drama", 5_000),                 # newer than the training split: support but no statistics
    entry(9_000_001, "Phim thử", "Crime|Drama", 0),                   # a demo movie
    entry(5, "No Genres Movie", "(no genres listed)", 10),
]
STATS = {296: (70_000, 70_000 * 4.20), 59114: (3_000, 3_000 * 3.40), 858: (47_000, 47_000 * 4.34), 1221: (31_000, 31_000 * 4.26),
         2023: (18_000, 18_000 * 3.90), 318: (73_945, 73_945 * 4.43), 3000: (1_500, 1_500 * 3.9), 3001: (2_200, 2_200 * 4.0)}
DELTAS = {318: (9, 45.0), 9_000_001: (2, 8.0)}


def ids(result):
    return [r.movie_id for r in result.rows]


def test_the_entry_keeps_the_genres_as_a_list_and_drops_the_no_genre_placeholder():
    e = entry(5, "X", "Crime|Drama")
    assert e.genres == ("Crime", "Drama") and e.genres_lc == ("crime", "drama")
    assert entry(6, "Y", "(no genres listed)").genres == ()
    assert entry(9_000_001, "Z").is_demo and not entry(8_999_999, "Z").is_demo


def test_tokens_are_lower_case_words():
    assert tokens("  Godfather   PART ") == ["godfather", "part"]
    assert tokens("") == [] and tokens(None) == []


def test_search_by_title_is_case_insensitive_and_needs_every_word():
    assert ids(search(CATALOG, STATS, {}, q="PULP", sort="title")) == [165863, 59114, 296]            # "marvel..." < "pulp (1972)" < "pulp fiction"
    assert set(ids(search(CATALOG, STATS, {}, q="pulp"))) == {296, 59114, 165863}
    assert set(ids(search(CATALOG, STATS, {}, q="godfather part"))) == {1221, 2023}
    assert set(ids(search(CATALOG, STATS, {}, q="1994"))) == {296, 318}                        # the year is part of the title
    assert ids(search(CATALOG, STATS, {}, q="zzzz")) == []


def test_an_empty_query_does_not_filter_by_name():
    assert search(CATALOG, STATS, {}, q="   ", size=50).total == len(CATALOG)


def test_filter_by_genre_ignores_case_and_combines_with_the_query():
    assert set(ids(search(CATALOG, STATS, {}, genre="western"))) == {3000, 3001}
    assert set(ids(search(CATALOG, STATS, {}, genre="WESTERN"))) == {3000, 3001}
    assert set(ids(search(CATALOG, STATS, {}, genre="Crime", q="godfather"))) == {858, 1221, 2023}
    assert search(CATALOG, STATS, {}, genre="Documentary", q="godfather").total == 0


def test_default_order_is_most_rated_first_and_ratings_include_the_new_ones():
    result = search(CATALOG, STATS, DELTAS, size=50)
    assert ids(result)[:3] == [318, 296, 858]
    shawshank = result.rows[0]
    assert shawshank.ratings == 102_929 + 9 and shawshank.new_ratings == 9 and shawshank.train_ratings == 73_945


def test_statistics_match_the_formula_and_are_missing_where_there_is_no_rating():
    rows = {r.movie_id: r for r in search(CATALOG, STATS, DELTAS, size=50).rows}
    s = rows[318]
    assert s.avg_rating == pytest.approx((73_945 * 4.43 + 45.0) / 73_954)
    assert s.wr == pytest.approx(weighted_rating(73_954, 73_945 * 4.43 + 45.0, M, C))
    assert rows[900001].avg_rating is None and rows[900001].wr is None and rows[900001].ratings == 5_000      # has a support, no statistics
    assert rows[5].avg_rating is None
    demo = rows[9_000_001]
    assert demo.is_demo and demo.ratings == 2 and demo.train_ratings == 0 and demo.new_ratings == 2          # a demo movie starts from the ledger
    assert demo.avg_rating == pytest.approx(4.0)


def test_sort_by_title_defaults_to_ascending_and_can_be_reversed():
    assert search(CATALOG, STATS, {}, sort="title", size=50).rows[0].movie_id == 900001           # "brand new" is first
    titles = [r.title.lower() for r in search(CATALOG, STATS, {}, sort="title", size=50).rows]
    assert titles == sorted(titles)
    desc = [r.title.lower() for r in search(CATALOG, STATS, {}, sort="title", order="desc", size=50).rows]
    assert desc == sorted(desc, reverse=True)


@pytest.mark.parametrize("sort", ["avg", "wr"])
def test_missing_values_come_last_in_both_directions(sort):
    for order in ("asc", "desc"):
        result = search(CATALOG, STATS, DELTAS, sort=sort, order=order, size=50)
        values = [getattr(r, "avg_rating" if sort == "avg" else "wr") for r in result.rows]
        present = [v for v in values if v is not None]
        assert values[: len(present)] == present and all(v is None for v in values[len(present):])        # no gaps before the end
        assert present == sorted(present, reverse=(order == "desc"))
        assert {900001, 5} <= {r.movie_id for r in result.rows[len(present):]}


@pytest.mark.parametrize("assume_sorted", [False, True])                              # True is the only mode the API uses
def test_ties_keep_movie_id_ascending_whatever_the_direction(assume_sorted):
    tie = [entry(30, "C", support=5), entry(10, "A", support=5), entry(20, "B", support=5)]
    if assume_sorted:
        tie.sort(key=lambda e: e.movie_id)                                          # the precondition of assume_sorted
    same_wr = {10: (100, 400.0), 20: (100, 400.0), 30: (100, 400.0)}
    for order in ("desc", "asc"):
        assert ids(search(tie, None, {}, sort="ratings", order=order, assume_sorted=assume_sorted)) == [10, 20, 30]
        assert ids(search(tie, same_wr, {}, sort="wr", order=order, assume_sorted=assume_sorted, m=M, c=C)) == [10, 20, 30]
        assert ids(search(tie, same_wr, {}, sort="avg", order=order, assume_sorted=assume_sorted, m=M, c=C)) == [10, 20, 30]


def test_page_and_size_must_be_at_least_one():
    for page, size in ((0, 20), (-1, 20), (1, 0), (1, -5)):
        with pytest.raises(ValueError, match="at least 1"):
            search(CATALOG, STATS, {}, page=page, size=size)


def test_pagination_and_pages():
    many = [entry(i, f"Movie {i:03d}", support=i) for i in range(1, 46)]
    first = search(many, None, {}, size=20, page=1)
    last = search(many, None, {}, size=20, page=3)
    assert (first.total, first.pages, len(first.rows)) == (45, 3, 20)
    assert len(last.rows) == 5 and last.rows[0].movie_id == 5                       # most rated first: ids 45..1, so page 3 holds 5, 4, 3, 2, 1
    beyond = search(many, None, {}, size=20, page=9)
    assert beyond.rows == () and beyond.total == 45 and beyond.pages == 3
    nothing = search(many, None, {}, q="nope")
    assert (nothing.total, nothing.pages, nothing.rows) == (0, 0, ())
    assert search(many, None, {}, size=45).pages == 1 and search(many, None, {}, size=44).pages == 2


def test_without_a_baseline_the_search_still_works_but_avg_and_wr_cannot_be_sorted():
    result = search(CATALOG, None, {}, q="godfather", sort="ratings")
    assert ids(result) == [858, 1221, 2023]
    assert all(r.avg_rating is None and r.wr is None for r in result.rows)
    for sort in ("avg", "wr"):
        with pytest.raises(StatsUnavailable, match="movie_stats"):
            search(CATALOG, None, {}, sort=sort)
    assert ids(search(CATALOG, None, {}, sort="title", size=3))                       # title still sorts


def test_bad_sort_or_order_is_refused():
    with pytest.raises(ValueError):
        search(CATALOG, STATS, {}, sort="popularity")
    with pytest.raises(ValueError):
        search(CATALOG, STATS, {}, order="sideways")


@pytest.mark.parametrize("mode", ["plain", "assume_sorted", "cached_order"])           # the API runs "cached_order": sorted once, filtered per search
def test_matches_a_brute_force_search_on_random_data(mode):
    rng = random.Random(5)
    orders = OrderCache() if mode == "cached_order" else None
    words = ["red", "blue", "night", "day", "city", "love", "war", "king"]
    genres = ["Drama", "Comedy", "Action", "Western", "Crime"]
    entries, stats = [], {}
    for i in range(1, 600):
        title = " ".join(rng.sample(words, 2)) + f" ({1950 + i % 70})"
        entries.append(entry(i, title, "|".join(rng.sample(genres, rng.randint(1, 3))), rng.randint(0, 5000)))
        if rng.random() < 0.6:
            n = rng.randint(1, 4000)
            stats[i] = (n, n * rng.uniform(2.0, 4.8))
    for q, genre, sort, order in [("night", None, "wr", "desc"), ("red city", "Drama", "avg", "asc"), ("", "Western", "ratings", "desc"),
                                  ("war", "crime", "title", "desc"), ("king", None, "ratings", "asc")]:
        for _ in range(2 if orders else 1):                                          # the second call of a cached order is a hit
            got = search(entries, stats, {}, q=q, genre=genre, sort=sort, order=order, size=50, m=M, c=C,
                         assume_sorted=mode != "plain", orders=orders)
        want = [e for e in entries if all(w in e.title_lc for w in q.split()) and (genre is None or genre.lower() in e.genres_lc)]

        def value(e):
            if sort == "title":
                return e.title_lc
            if sort == "ratings":
                return e.support
            if e.movie_id not in stats:
                return None
            n, s = stats[e.movie_id]
            return s / n if sort == "avg" else weighted_rating(n, s, M, C)

        # reference with the documented tie rule: key then movieId ascending, direction applied to the key only
        keyed = sorted([e for e in want if value(e) is not None], key=lambda e: e.movie_id)
        keyed = sorted(keyed, key=value, reverse=(order == "desc"))
        missing = sorted([e for e in want if value(e) is None], key=lambda e: e.movie_id)
        assert [r.movie_id for r in got.rows] == [e.movie_id for e in (keyed + missing)][:50], (q, genre, sort, order)
        assert got.total == len(want) and got.pages == math.ceil(len(want) / 50)


class CountingRepo:
    def __init__(self, docs):
        self.docs = docs
        self.reads = 0

    def get_catalog(self):
        self.reads += 1
        return self.docs


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_the_cache_reads_once_serves_the_old_copy_while_refreshing_and_invalidate_forces_a_read():
    repo, clock = CountingRepo([{"_id": 2, "title": "B", "genres": "Drama", "support": 1}, {"_id": 1, "title": "A", "genres": "Drama", "support": 1}]), Clock()
    cache = CatalogCache(repo, 9_000_000, clock=clock)
    for _ in range(30):
        assert [e.movie_id for e in cache.get()] == [1, 2]                      # sorted by movieId once, whatever order Mongo returned
    assert repo.reads == 1
    clock.now += 31                                                              # expired: the caller still gets the old copy at once
    repo.docs.append({"_id": 3, "title": "C", "genres": "Drama", "support": 1})
    assert len(cache.get()) == 2
    cache.wait()
    assert repo.reads == 2 and len(cache.get()) == 3                             # the refresh ran in the background
    repo.docs.append({"_id": 4, "title": "D", "genres": "Drama", "support": 1})
    assert len(cache.get()) == 3 and repo.reads == 2                             # fresh again: no read
    cache.invalidate()
    assert len(cache.get()) == 4 and repo.reads == 3                             # a demo movie changed: the next request waits and sees it


def test_a_failed_background_refresh_keeps_the_old_copy_and_retries_soon():
    repo, clock = CountingRepo([{"_id": 1, "title": "A", "genres": "Drama", "support": 1}]), Clock()
    cache = CatalogCache(repo, 9_000_000, clock=clock)
    assert len(cache.get()) == 1
    clock.now += 31
    broken = repo.get_catalog
    repo.get_catalog = lambda: (_ for _ in ()).throw(RuntimeError("mongo gone"))
    assert len(cache.get()) == 1
    cache.wait()
    assert len(cache.get()) == 1                                                  # still served
    repo.get_catalog = broken
    clock.now += 10                                                               # a few seconds later it tries again
    cache.get()
    cache.wait()
    assert repo.reads == 2


# ---- OrderCache: the catalog is sorted once per data snapshot, not per request ------------------------------------------------

def test_the_order_is_built_once_for_the_same_data_and_again_when_the_data_changes(monkeypatch):
    calls = []
    real = catalog_module._order
    monkeypatch.setattr(catalog_module, "_order", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    orders = OrderCache()
    entries = sorted(CATALOG, key=lambda e: e.movie_id)

    def run(deltas, sort="wr", **kw):
        return search(entries, STATS, deltas, sort=sort, size=50, m=M, c=C, assume_sorted=True, orders=orders, **kw)

    full = run(DELTAS)
    for q in ("", "godfather", "pulp", "shane"):                                    # other filters on the same order: no new sort
        run(DELTAS, q=q)
    assert len(calls) == 1 and ids(full) == ids(search(entries, STATS, DELTAS, sort="wr", size=50, m=M, c=C, assume_sorted=True))
    run(dict(DELTAS))                                                                # a new deltas object (a rating arrived): rebuilt
    assert len(calls) == 3                                                           # (one for the cached call, one for the uncached reference above)
    run(DELTAS, order="asc")                                                         # another direction is another order
    assert len(calls) == 4
    run({}, sort="title")
    run({1: (1, 1.0)}, sort="title")                                                 # a title order does not depend on the ratings
    assert len(calls) == 5


def test_concurrent_requests_for_one_order_build_it_once():
    orders = OrderCache()
    built, started, release = [], threading.Event(), threading.Event()
    sources = (object(),)

    def build():
        built.append(1)
        started.set()
        assert release.wait(5)
        return ["order"]

    results = []
    threads = [threading.Thread(target=lambda: results.append(orders.get("k", sources, build))) for _ in range(4)]
    threads[0].start()
    assert started.wait(5)                                                           # the first one is sorting
    for t in threads[1:]:
        t.start()
    time.sleep(0.1)
    release.set()
    for t in threads:
        t.join(5)
    assert len(built) == 1 and len(results) == 4 and all(r is results[0] for r in results)


def test_the_number_of_kept_orders_is_bounded():
    orders = OrderCache()
    sources = (object(),)
    for i in range(MAX_ORDERS * 3):                                                  # m comes from configuration, but never let keys pile up
        orders.get(("wr", True, float(i), 3.5, True), sources, lambda: [])
    assert len(orders._orders) <= MAX_ORDERS


# ---- CatalogCache: a failed thread start, invalidate during a refresh ---------------------------------------------------------

def test_a_refresh_thread_that_cannot_start_does_not_leave_the_catalog_locked(monkeypatch, caplog):
    repo, clock = CountingRepo([{"_id": 1, "title": "A", "genres": "Drama", "support": 1}]), Clock()
    cache = CatalogCache(repo, 9_000_000, clock=clock)
    assert len(cache.get()) == 1
    clock.now += 31

    class NoThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")

    with monkeypatch.context() as patch:
        patch.setattr(catalog_module.threading, "Thread", NoThread)
        assert len(cache.get()) == 1                                                 # the previous copy is served, no error
    assert "could not start" in caplog.text
    assert cache._lock.acquire(blocking=False)                                       # not held forever
    cache._lock.release()
    repo.docs.append({"_id": 2, "title": "B", "genres": "Drama", "support": 1})
    clock.now += 10                                                                  # a few seconds later the refresh works again
    cache.get()
    cache.wait()
    assert repo.reads == 2 and len(cache.get()) == 2


def test_invalidate_does_not_wait_for_a_refresh_and_the_refresh_does_not_publish_an_older_read():
    started, release = threading.Event(), threading.Event()

    class SlowSecondRead(CountingRepo):
        def get_catalog(self):
            self.reads += 1
            snapshot = list(self.docs)                                               # what this read sees: the data before the admin's change
            if self.reads == 2:
                started.set()
                assert release.wait(5)
            return snapshot

    repo, clock = SlowSecondRead([{"_id": 1, "title": "A", "genres": "Drama", "support": 1}]), Clock()
    cache = CatalogCache(repo, 9_000_000, clock=clock)
    assert len(cache.get()) == 1
    clock.now += 31
    cache.get()                                                                      # starts the background refresh (read 2)
    assert started.wait(5)
    repo.docs.append({"_id": 2, "title": "B", "genres": "Drama", "support": 1})      # an admin adds a movie while that read is in progress
    t0 = time.monotonic()
    cache.invalidate()
    assert time.monotonic() - t0 < 1.0                                               # POST /movies is not held up by the read
    release.set()
    cache.wait()
    assert [e.movie_id for e in cache.get()] == [1, 2] and repo.reads == 3           # the older read was not kept: the next request reads again
