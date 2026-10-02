# fakes.py — in-memory ServingRepository double for unit-testing service.py (and the
# FastAPI wiring in test_api.py) without a live MongoDB. Implements the exact
# ServingRepository Protocol from src/serving/repository.py.
from __future__ import annotations

from serving.models import HistorySnapshot
from serving.repository import ActivePointer


class FakeServingRepository:
    def __init__(
        self,
        active_version: str = "v1.0.0",
        artifacts: dict[str, str] | None = None,
        histories: dict[int, HistorySnapshot] | None = None,
        user_recs: dict[tuple[int, str], list[dict]] | None = None,
        similar: dict[tuple[int, str], list[dict]] | None = None,
        popular: dict[str, list[dict]] | None = None,
        rated: dict[int, frozenset[int]] | None = None,
        movies: dict[int, dict] | None = None,
        rating_events: dict[str, dict] | None = None,
        pipeline_state: dict | None = None,
        model_registry: list[dict] | None = None,
        retrain_progress: dict | None = None,
        stars: dict[int, dict[int, float]] | None = None,
    ):
        self.active_version = active_version
        self.artifacts = artifacts or {
            "user_recommendations": active_version,
            "similar_movies": active_version,
            "popular_movies": active_version,
        }
        self.histories = histories or {}
        self.user_recs = user_recs or {}
        self.similar = similar or {}
        self.popular = popular or {}
        self.rated = rated or {}
        self.movies = movies or {}
        self.rating_events = rating_events or {}
        self.pipeline_state = pipeline_state
        self.stars = stars or {}   # userId -> {movieId: stars}, for get_rating_history
        self.model_registry = model_registry or []
        self.retrain_progress = retrain_progress or {"pending": 0, "watermark": None}
        self.calls: list[str] = []  # method-call log, used to assert "no store lookup" on invalid input

    def get_active_pointer(self) -> ActivePointer:
        self.calls.append("get_active_pointer")
        return ActivePointer(model_version=self.active_version, artifacts=self.artifacts)

    def get_user_history(self, user_id: int) -> HistorySnapshot | None:
        return self.histories.get(user_id)

    def get_user_recommendations(self, user_id: int, model_version: str) -> list[dict] | None:
        return self.user_recs.get((user_id, model_version))

    def get_similar_movies(self, movie_ids: list[int], model_version: str) -> dict[int, list[dict]]:
        result = {}
        for mid in movie_ids:
            items = self.similar.get((mid, model_version))
            if items:
                result[mid] = items
        return result

    def get_popular_movies(self, model_version: str) -> list[dict]:
        return self.popular.get(model_version, [])

    def get_rated_movie_ids(self, user_id: int, candidate_ids: frozenset[int]) -> frozenset[int]:
        return frozenset(candidate_ids) & self.rated.get(user_id, frozenset())

    def get_movies(self, movie_ids: frozenset[int]) -> dict[int, dict]:
        return {mid: self.movies[mid] for mid in movie_ids if mid in self.movies}

    def movie_exists(self, movie_id: int) -> bool:
        return movie_id in self.movies

    def get_rating_event(self, event_id: str) -> dict | None:
        return self.rating_events.get(event_id)

    def get_pipeline_state(self) -> dict | None:
        return self.pipeline_state

    def get_rating_history(self, user_id: int, limit: int) -> tuple[int, list[dict]]:
        self.calls.append("get_rating_history")
        snapshot = self.histories.get(user_id)
        if snapshot is None:
            return 0, []
        ids = list(snapshot.recent_movie_ids)[:limit]
        items = [
            {
                "movieId": mid,
                "rating": self.stars.get(user_id, {}).get(mid),
                "title": self.movies.get(mid, {}).get("title", ""),
                "genres": self.movies.get(mid, {}).get("genres", ""),
                "inCatalog": mid in self.movies,
            }
            for mid in ids
        ]
        return snapshot.interaction_count, items

    def get_demo_movies(self, id_range_start: int, since) -> list[dict]:
        return [
            {"_id": mid, **doc}
            for mid, doc in self.movies.items()
            if mid >= id_range_start and doc.get("addedAt") is not None and doc["addedAt"] >= since
        ]

    def create_demo_movie(self, title: str, genres: list[str], id_range_start: int, now) -> dict:
        # monotonic like the Mongo counter: a deleted movie's id is never handed out again
        new_id = max(getattr(self, "_demo_seq", id_range_start - 1), id_range_start - 1) + 1
        self._demo_seq = new_id
        doc = {"title": title, "genres": "|".join(genres), "support": 0, "addedAt": now}
        self.movies[new_id] = doc
        return {"_id": new_id, **doc}

    def delete_demo_movie(self, movie_id: int, id_range_start: int) -> bool:
        if movie_id < id_range_start or movie_id not in self.movies:
            return False
        del self.movies[movie_id]
        return True

    def get_model_registry(self) -> list[dict]:
        return self.model_registry

    def get_retrain_progress(self) -> dict:
        return self.retrain_progress
