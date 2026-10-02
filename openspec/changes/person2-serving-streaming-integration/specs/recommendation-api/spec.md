## ADDED Requirements

### Requirement: Recommendation endpoint and input validation
The API SHALL expose `GET /recommendations/{userId}?k=<int>` where `userId` MUST be a positive integer and `k` MUST be an integer within configured bounds (default 10, minimum 1, maximum 50); invalid input SHALL be rejected with HTTP 422 and no store lookup.

#### Scenario: Default k
- **WHEN** a client calls `GET /recommendations/1` without `k`
- **THEN** the response contains at most 10 recommendations

#### Scenario: Out-of-bounds k
- **WHEN** a client calls with `k=0` or `k=51`
- **THEN** the API returns HTTP 422 with a validation message

#### Scenario: Unknown user is valid
- **WHEN** a client requests a positive `userId` that has no `user_history` document
- **THEN** the API returns HTTP 200 with tier `0_history` rather than an error

### Requirement: Response contract
Every successful response SHALL contain `userId`, `strategy`, `modelVersion`, `generatedAt` and `recommendations[]`, plus the additive fields `tier` and `fallbackReason` (null when no fallback occurred); each recommendation item SHALL contain `movieId`, `title`, `genres`, `rank`, `score` and `source`.

#### Scenario: modelVersion always present
- **WHEN** any tier or fallback path produces a response
- **THEN** `modelVersion` equals the active release version recorded in `serving_meta`

#### Scenario: Enriched items
- **WHEN** recommendations are returned
- **THEN** every item has a non-empty `title` and `genres` taken from the `movies` collection and ranks are consecutive starting at 1

### Requirement: History-tier routing with tunable threshold
The router SHALL read `interaction_count` from `user_history` (absent document means 0) and select tier `0_history` when it equals 0, `few_history` when it is between 1 and T−1, and `enough_history` when it is at least T, where T is read from configuration.

#### Scenario: Zero history
- **WHEN** a user has `interaction_count = 0`
- **THEN** the response has tier `0_history`, strategy `POPULARITY`, and items come from the active `popular_movies` list

#### Scenario: Few history
- **WHEN** a user has `1 ≤ interaction_count < T`
- **THEN** the response has tier `few_history`, strategy `CONTENT+POPULARITY`, and candidates come from `similar_movies` of the user's positive (else recent) movies complemented by popularity

#### Scenario: Enough history
- **WHEN** a user has `interaction_count ≥ T` and an active `user_recommendations` document exists
- **THEN** the response has tier `enough_history`, strategy `ALS+CONTENT`, and ALS items are the primary source

### Requirement: Degradation chain with logged reason
When a tier's primary source is unavailable, the router SHALL degrade ALS → Content → Popularity and SHALL set `fallbackReason` to one of `als_artifact_missing`, `no_content_candidates` or `filled_from_popularity`.

#### Scenario: Cold-start user without ALS document
- **WHEN** a user with `interaction_count ≥ T` has no `user_recommendations` document for the active version
- **THEN** the response uses content candidates from the user's history complemented by popularity and `fallbackReason = "als_artifact_missing"`

#### Scenario: Not enough candidates
- **WHEN** fused candidates after exclusion number fewer than k
- **THEN** remaining slots are filled from the popularity list (excluding already-rated and duplicates) and `fallbackReason = "filled_from_popularity"`

### Requirement: Exact already-rated exclusion
No response SHALL contain a movie the user has rated, including ratings ingested by streaming after the artifact was precomputed; exclusion MUST use the `user_rated` collection.

#### Scenario: Fresh rating excluded
- **WHEN** a user rates, via the stream, a movie that is in their active ALS list and then requests recommendations
- **THEN** that movie is absent from the response

#### Scenario: Old rating excluded from content candidates
- **WHEN** content candidates include a movie the user rated long before their most recent R ratings
- **THEN** that movie is absent from the response

### Requirement: Rank-based fusion and deterministic ordering
When multiple sources are selected, the API SHALL fuse them with weighted reciprocal rank fusion using configured weights, SHALL break ties in content similarity by movie `support` descending and then `movieId` ascending, and SHALL produce identical output for identical store state and input.

#### Scenario: Determinism
- **WHEN** the same request is issued twice with no store change in between
- **THEN** both responses have identical recommendation lists and scores

### Requirement: Threshold T chosen by recorded experiment
The value of T SHALL be chosen by an offline experiment that compares ALS, Content and Popularity HitRate@10 and NDCG@10 on the same user set per training-history bucket using a decision rule fixed before the run, and the result SHALL be recorded in `evidence/p2_tier_threshold.csv` and `docs/MODEL_DESIGN.md`.

#### Scenario: Same user set per bucket
- **WHEN** the experiment reports metrics for a bucket
- **THEN** all three strategies are evaluated on exactly the same users, and the bucket's user count and 95% confidence intervals are reported

#### Scenario: No leakage from precomputed artifacts
- **WHEN** ALS candidates are generated for the experiment
- **THEN** they come from `ALSModel.load` excluding only items rated before `cut_test`, not from `als_topn.json`

### Requirement: Request observability
The API SHALL write one structured log record per request with `userId`, `tier`, `strategy`, `fallbackReason`, `modelVersion`, `k`, number returned and latency, and a summary script SHALL report strategy distribution, fallback rate and p50/p95 latency.

#### Scenario: Latency evidence
- **WHEN** the load script sends at least 1,000 requests across all tiers
- **THEN** the summary evidence reports p50 and p95 latency, the strategy distribution and the fallback rate
