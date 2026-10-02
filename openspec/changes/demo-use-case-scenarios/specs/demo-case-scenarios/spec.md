## ADDED Requirements

### Requirement: Case-test selector
When `api.demo_enabled` is true, the demo page SHALL offer a "Case test" dropdown whose options are the team's use cases 1–9 plus two serving cases: "user đã có rating và có ALS" and "user đủ lịch sử nhưng thiếu ALS". Selecting an option SHALL load the user that represents that case and render that case's explanation card. The free `userId` input SHALL remain available alongside the dropdown.

#### Scenario: Case 1 always uses a fresh user
- **WHEN** the presenter selects case 1 twice in a row
- **THEN** each selection loads a different random `userId` that has no `user_history` document, and the response shows tier `0_history` with strategy `POPULARITY`

#### Scenario: Case 8 loads a user with a few ratings
- **WHEN** the presenter selects case 8 after the seeding script has run
- **THEN** the page loads a seeded user whose `interaction_count` is between 1 and T−1, and the response shows tier `few_history`

#### Scenario: Missing-ALS case shows the fallback
- **WHEN** the presenter selects "user đủ lịch sử nhưng thiếu ALS"
- **THEN** the page loads user `127249` and the panel shows `fallbackReason: als_artifact_missing` highlighted

### Requirement: Case card mirrors the team's table
For every case, the page SHALL display the five columns of the team's use-case table (Điều gì xảy ra, Recommendation, Streaming, ALS Retrain, Chốt) as the expected behaviour, and SHALL display the observed `tier` and `strategy` from the live response next to the expected Recommendation.

#### Scenario: Expected and observed side by side
- **WHEN** the presenter selects case 8
- **THEN** the card shows the expected "Content / Hybrid, sau đó chuyển dần sang ALS" next to the observed `few_history` / `CONTENT+POPULARITY`

#### Scenario: Case 7 reuses case 1
- **WHEN** the presenter selects case 7
- **THEN** the card states that the team decided case 7 behaves like case 1, and the page loads a fresh user exactly as case 1 does

### Requirement: Seeded case users
A seeding script SHALL create the users needed by cases that require pre-existing history (at least case 8) by publishing ratings through `POST /ratings` with deterministic `eventId`s, so that the data passes through the same Kafka → Structured Streaming path as any other rating, and re-running the script has no additional effect.

#### Scenario: Re-running the seeding script
- **WHEN** the seeding script is run twice against the running stack
- **THEN** after the pipeline applies the events, the seeded users' `interaction_count` and the number of `rating_events` documents with the seeded `eventId`s are the same as after the first run

#### Scenario: Seeded data is consistent across both stores
- **WHEN** a seeded rating has been applied
- **THEN** it is present in `user_rated`, reflected in `user_history`, and appended to `curated_ratings`, exactly like a rating posted from the demo page

### Requirement: Model lifecycle and retrain progress view
When `api.demo_enabled` is true, the API SHALL expose `GET /debug/system` returning: the active `modelVersion`; every `model_registry` version with its `status`, `importedAt`, `activatedAt` and the name and pass/fail result of each gate check; and retrain progress, defined as the number of `rating_events` whose `ingestedAt` is later than `pipeline_state.retrain_handoff.watermark` (the epoch when no watermark exists) together with `n_min_events` read from `configs/streaming.yaml`. When the flag is false, the route SHALL return HTTP 404. The page SHALL show this data for cases 5 and 6 and MUST NOT offer any control that starts retraining or changes the active version.

#### Scenario: Rejected candidate is visible
- **WHEN** the presenter selects case 6
- **THEN** the panel lists `v1.0.0` as `active` and `v1.1.0` as `rejected`, together with the gate checks that failed

#### Scenario: Retrain progress counts new applied events
- **WHEN** N new ratings are applied by the pipeline after the last handoff watermark
- **THEN** the pending count returned by `GET /debug/system` increases by N, and the page shows it against `n_min_events`

#### Scenario: Disabled outside demo
- **WHEN** `api.demo_enabled` is false
- **THEN** `GET /debug/system` returns HTTP 404

#### Scenario: No lifecycle controls
- **WHEN** the presenter views cases 5 or 6
- **THEN** the page contains no button or form that triggers `retrain_trigger`, the promotion gate, or a change of `serving_meta`

### Requirement: Configurable rating confirmation wait
The page SHALL poll `GET /ratings/{eventId}` about once per second for up to `api.rating_poll_timeout_seconds` (default 60), a value obtained from the API, before logging the "Streaming pipeline có đang chạy không?" hint.

#### Scenario: Slow but healthy pipeline
- **WHEN** a rating takes 45 seconds to be applied while the pipeline is running
- **THEN** the page shows no timeout hint and reloads the recommendations once the rating is applied

#### Scenario: Pipeline stopped
- **WHEN** the pipeline is stopped and the presenter rates a movie
- **THEN** after the configured timeout the log shows the hint
