# config.py — load configs/serving.yaml (+ env for secrets). No hardcoded paths/credentials
# (README convention; specs/serving-runtime "Configuration without hardcoded paths or credentials").
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "serving.yaml"


@dataclass(frozen=True)
class FusionConfig:
    rrf_k: int
    weight_popularity_in_few: float
    weight_content_in_enough: float


@dataclass(frozen=True)
class RoutingConfig:
    threshold_t: int
    seeds_per_user: int
    recent_cap: int
    positive_cap: int
    fusion: FusionConfig


@dataclass(frozen=True)
class MongoConfig:
    uri: str
    db: str
    collections: dict[str, str]
    serving_meta_cache_ttl_seconds: int


@dataclass(frozen=True)
class ApiConfig:
    host: str
    port: int
    k_default: int
    k_min: int
    k_max: int
    demo_enabled: bool
    kafka_bootstrap_servers_env: str
    ratings_topic: str
    produce_timeout_seconds: int
    rating_poll_timeout_seconds: int = 60
    ui: str = "legacy"          # which pages /app, /admin and /demo serve: "legacy" (static files) or "react" (web/ build)


@dataclass(frozen=True)
class NewItemsConfig:
    enabled: bool = False
    slots: int = 1
    position: int = 3
    window_days: int = 30
    id_range_start: int = 9_000_000


@dataclass(frozen=True)
class PopularityConfig:
    """Live weighted-rating popularity (change live-weighted-popularity). `live` false = the popular_movies.json
    artifact only, which is also what a configuration without a `popularity` block gives."""
    live: bool = False
    m: float = 1000.0                   # WR = v/(v+m)*R + m/(v+m)*C
    min_support: int = 100              # ratings a movie needs (baseline + new) to be eligible
    top_n: int = 10                     # list size, same as the artifact
    cache_ttl_seconds: float = 2.0      # a computed list is reused for this long


@dataclass(frozen=True)
class ServingConfig:
    mongo: MongoConfig
    api: ApiConfig
    routing: RoutingConfig
    active_model_version: str
    api_log_path: str
    new_items: NewItemsConfig = NewItemsConfig()
    retrain_n_min_events: int = 50
    popularity: PopularityConfig = PopularityConfig()


UI_CHOICES = ("legacy", "react")


def _popularity_config(raw: dict | None) -> PopularityConfig:
    """Validate the `popularity` block; every message names the offending key."""
    raw = raw or {}
    live = raw.get("live", False)
    if not isinstance(live, bool):
        raise ValueError(f"popularity.live must be true or false, got {live!r}")

    def number(key: str, default, kind):
        value = raw.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"popularity.{key} must be a number, got {value!r}")
        if kind is int and isinstance(value, float) and not value.is_integer():
            raise ValueError(f"popularity.{key} must be a whole number, got {value!r}")
        return kind(value)

    m = number("m", 1000, float)
    min_support = number("min_support", 100, int)
    top_n = number("top_n", 10, int)
    ttl = number("cache_ttl_seconds", 2, float)
    if m < 0:
        raise ValueError(f"popularity.m must be >= 0, got {m}")
    if min_support < 1:
        raise ValueError(f"popularity.min_support must be >= 1, got {min_support}")
    if not 1 <= top_n <= 50:
        raise ValueError(f"popularity.top_n must be between 1 and 50, got {top_n}")
    if ttl < 0:
        raise ValueError(f"popularity.cache_ttl_seconds must be >= 0, got {ttl}")
    return PopularityConfig(live=live, m=m, min_support=min_support, top_n=top_n, cache_ttl_seconds=ttl)


def _ui_choice(value: object) -> str:
    text = str(value).strip().lower()
    if text not in UI_CHOICES:
        raise ValueError(f"api.ui must be one of {UI_CHOICES}, got {value!r}")
    return text


def load_serving_config(path: Path | None = None) -> ServingConfig:
    path = path or DEFAULT_CONFIG_PATH
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    mongo_raw = raw["mongo"]
    mongo_uri = os.environ.get(mongo_raw["uri_env"], "mongodb://localhost:27017")

    fusion_raw = raw["routing"]["fusion"]
    new_items_raw = raw.get("new_items") or {}
    streaming_path = path.parent / "streaming.yaml"
    streaming_raw = yaml.safe_load(streaming_path.read_text(encoding="utf-8")) if streaming_path.exists() else {}
    n_min_events = int((streaming_raw.get("retrain_trigger") or {}).get("n_min_events", 50))
    return ServingConfig(
        mongo=MongoConfig(
            uri=mongo_uri,
            db=mongo_raw["db"],
            collections=dict(mongo_raw["collections"]),
            serving_meta_cache_ttl_seconds=int(mongo_raw["serving_meta_cache_ttl_seconds"]),
        ),
        api=ApiConfig(
            host=raw["api"]["host"],
            port=int(raw["api"]["port"]),
            k_default=int(raw["api"]["k_default"]),
            k_min=int(raw["api"]["k_min"]),
            k_max=int(raw["api"]["k_max"]),
            demo_enabled=bool(raw["api"].get("demo_enabled", False)),
            kafka_bootstrap_servers_env=raw["api"].get("kafka_bootstrap_servers_env", "KAFKA_BOOTSTRAP_SERVERS"),
            ratings_topic=raw["api"].get("ratings_topic", "ratings.v1"),
            produce_timeout_seconds=int(raw["api"].get("produce_timeout_seconds", 10)),
            rating_poll_timeout_seconds=int(raw["api"].get("rating_poll_timeout_seconds", 60)),
            ui=_ui_choice(raw["api"].get("ui", "legacy")),
        ),
        routing=RoutingConfig(
            threshold_t=int(raw["routing"]["T_few_enough"]),
            seeds_per_user=int(raw["routing"]["seeds_per_user"]),
            recent_cap=int(raw["routing"]["recent_cap"]),
            positive_cap=int(raw["routing"]["positive_cap"]),
            fusion=FusionConfig(
                rrf_k=int(fusion_raw["rrf_k"]),
                weight_popularity_in_few=float(fusion_raw["weight_popularity_in_few"]),
                weight_content_in_enough=float(fusion_raw["weight_content_in_enough"]),
            ),
        ),
        active_model_version=raw["active_model_version"],
        api_log_path=raw["logging"]["api_log_path"],
        new_items=NewItemsConfig(
            enabled=bool(new_items_raw.get("enabled", False)),
            slots=int(new_items_raw.get("slots", 1)),
            position=int(new_items_raw.get("position", 3)),
            window_days=int(new_items_raw.get("window_days", 30)),
            id_range_start=int(new_items_raw.get("id_range_start", 9_000_000)),
        ),
        retrain_n_min_events=n_min_events,
        popularity=_popularity_config(raw.get("popularity")),
    )
