## ADDED Requirements

### Requirement: Demo page served by the API
When `api.demo_enabled` is true, the API SHALL serve a single self-contained HTML page at `GET /demo` that loads no resources from the internet (no CDN scripts, web fonts or remote images); when the flag is false, `GET /demo` SHALL return HTTP 404.

#### Scenario: Offline demo
- **WHEN** the demo page is opened with the laptop disconnected from the internet but the Docker stack running
- **THEN** the page renders fully and all interactions work

#### Scenario: Disabled in production
- **WHEN** `api.demo_enabled` is false
- **THEN** `GET /demo` and `GET /debug/users/{userId}` both return HTTP 404

### Requirement: Page talks only to the API
The demo page SHALL obtain all data exclusively through the Recommendation API's HTTP routes and MUST NOT read MongoDB, Kafka or Parquet directly, so the demo exercises the same path a real client would.

#### Scenario: Network trace
- **WHEN** the browser's network log is inspected during a full demo run
- **THEN** every request targets the API origin (`/recommendations`, `/ratings`, `/debug/users`, `/demo`)

### Requirement: User selection and recommendations view
The page SHALL let the presenter enter any `userId` or pick one of three presets — a fresh random user (no history), user `1` (has an ALS document), user `127249` (history but no ALS document) — and SHALL show the recommendations as cards with title, genres, rank and source.

#### Scenario: Three tiers side by side
- **WHEN** the presenter selects each preset in turn
- **THEN** the page shows tier `0_history` / `POPULARITY`, then `enough_history` / `ALS+CONTENT`, then `enough_history` / `CONTENT+POPULARITY` with fallback `als_artifact_missing`

### Requirement: "Inside the system" panel
The page SHALL display, next to the recommendations, the response's `tier`, `strategy`, `fallbackReason`, `modelVersion` and measured request latency, plus `interaction_count` and the last streaming batch from `GET /debug/users/{userId}`, and a timestamped event log of the presenter's actions.

#### Scenario: Fallback visible
- **WHEN** recommendations are loaded for a user without an ALS document
- **THEN** the panel shows `fallbackReason: als_artifact_missing` visibly highlighted

### Requirement: Debug state endpoint
When `api.demo_enabled` is true, the API SHALL expose `GET /debug/users/{userId}` returning the user's `interaction_count`, `recent_movieIds`, `positive_movieIds`, `lastUpdated`, the pipeline's last committed batch id and run time, and the active `modelVersion`.

#### Scenario: Unknown user
- **WHEN** the debug endpoint is called for a user with no history
- **THEN** it returns HTTP 200 with `interaction_count: 0` and empty lists

### Requirement: Rate-and-observe loop
Each card SHALL offer a 1–5 star control; clicking a star SHALL post the rating with a browser-generated `eventId`, log the 202 acknowledgement, poll `GET /ratings/{eventId}` about once per second for up to 30 seconds, and on `applied` reload the recommendations and panel and highlight what changed; on timeout it SHALL log a hint that the streaming pipeline may not be running.

#### Scenario: New user moves up a tier
- **WHEN** the presenter rates 3 movies for a fresh user and each becomes `applied`
- **THEN** the panel's tier changes from `0_history` to `few_history` and the change is highlighted

#### Scenario: Rated movie disappears
- **WHEN** the presenter rates the first recommended movie for user `1` and it becomes `applied`
- **THEN** the reloaded recommendations no longer contain that movie, and the log notes its removal

#### Scenario: Pipeline stopped during demo
- **WHEN** the streaming pipeline is stopped and the presenter rates a movie
- **THEN** after 30 seconds the log shows the "pipeline may not be running" hint, and the rating is still applied once the pipeline is restarted
