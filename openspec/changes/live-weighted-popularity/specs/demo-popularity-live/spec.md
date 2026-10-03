## ADDED Requirements

### Requirement: Popularity debug endpoint
The API SHALL provide `GET /debug/popularity`, answering 404 when `api.demo_enabled` is false. Query parameters: `n` (1–50, default 10), `m` (0–100000, default the configured value), `deltas` (default true). The route SHALL work whether or not `popularity.live` is on. The response SHALL contain `source` (`live` or `artifact`), `liveEnabled` (the value of `popularity.live`, i.e. whether `/recommendations` uses the live list), `preview` (true when `m` differs from the configured value), `m`, `c`, `minSupport`, `baseline` (`generatedAt`, `cutoff`, `ratings`, or null), `appliedEvents`, `generatedAt` and `items`, each item with `rank`, `movieId`, `title`, `genres`, `avgRating`, `support`, `baseSupport`, `newRatings`, `wr` and `baseRank` (rank in the baseline-only ordering with the same `m`, null beyond rank 200). With `deltas=false` the ledger is ignored. Out-of-range parameters SHALL give 422. When the artifact is the source, `avgRating` is null and `newRatings` is 0.

#### Scenario: Live list with the evidence behind it
- **WHEN** the demo flag is on, live popularity is enabled and a client requests `/debug/popularity?n=10`
- **THEN** the response lists 10 items with their average rating, rating count, count of new ratings, WR and baseline rank, and `source` is `live`

#### Scenario: Preview with another m
- **WHEN** a client requests `/debug/popularity?m=0`
- **THEN** `preview` is true, items are ordered by raw average rating among movies with at least `minSupport` ratings, and serving is unchanged (a recommendation request still uses the configured `m`)

#### Scenario: Baseline only
- **WHEN** a client requests `/debug/popularity?deltas=false`
- **THEN** every item has `newRatings` 0 and `appliedEvents` is 0

#### Scenario: Live switch off
- **WHEN** `popularity.live` is false and a baseline exists
- **THEN** the route still answers with `source` `live` and `liveEnabled` false, and `/recommendations` keeps using the artifact

#### Scenario: Demo off
- **WHEN** `api.demo_enabled` is false
- **THEN** the route answers 404, also for out-of-range parameters

#### Scenario: Bad parameter
- **WHEN** a client requests `/debug/popularity?n=0` or `?m=-1`
- **THEN** the API answers 422

### Requirement: Admin "Popularity" section
The admin page SHALL have a section `#/popularity` that shows the top 10 from `/debug/popularity` with rank, title, average rating, rating count (with the number of new ratings), WR and the rank change against the baseline. It SHALL refresh every 3 seconds only while the browser tab is visible and the section is open. A movie whose rank changed since the previous refresh SHALL be marked with an arrow and a text ("up 1", "down 2"), not by colour alone, and any highlight animation SHALL respect `prefers-reduced-motion`. Selecting a row SHALL open a step-by-step formula panel that substitutes the movie's numbers into `v/(v+m)·R + m/(v+m)·C` and states the weight `v/(v+m)` in words. An input for `m` SHALL be labelled as a preview that does not change the system, and a notice SHALL be shown while a preview value is active.

#### Scenario: A rating changes the table
- **WHEN** a rating is applied that moves Seven Samurai above the movie ranked above it
- **THEN** within one refresh the table shows Seven Samurai one rank higher with an "up 1" marker and its rating count shows "+n new"

#### Scenario: Polling stops when hidden
- **WHEN** the browser tab is hidden or another admin section is open
- **THEN** no `/debug/popularity` request is sent

#### Scenario: Formula panel
- **WHEN** the presenter selects a row
- **THEN** the panel shows `v`, `R`, `C`, `m`, the weight `v/(v+m)` as a percentage, and the resulting WR equal to the table value

#### Scenario: Preview m
- **WHEN** the presenter enters `m = 0`
- **THEN** the table is replaced by the preview list, a notice says it is a preview, and clearing the field restores the live list

#### Scenario: Artifact fallback is visible
- **WHEN** the API reports `source = artifact`
- **THEN** the section says the live statistics are not available and shows the artifact list without average ratings

### Requirement: Live demo script
`scripts/wr_live_demo.py`, using only the standard library, SHALL provide the commands `check`, `plan`, `inject` and `spam`, each accepting `--api` and `--dry-run`. `check` SHALL compare the baseline-only top 10 with `artifacts/popular_movies.json` (same movieIds in the same order, WR within the artifact's own rounding of 0.0005, float noise included) and exit non-zero on a difference. `plan` SHALL print, for each adjacent pair in the live top 12, how many 5-star ratings the lower movie needs to pass the upper one, computed from the exact values returned by the API, and name the closest pair. `inject` SHALL send N ratings from synthetic users in the range 999200001 and above, skipping users that already have history, using the eventId `uuid5(namespace, "wr-live-demo:<user>:<movie>")` so a re-run is idempotent, retrying with the same eventId on 503, waiting for every event to be `applied` (as long as the API's rating poll timeout plus 0.2 s per rating), and printing the table before and after with rank changes. `spam` SHALL do the same for a low-support movie, printing WR at 10 and 100 added ratings and the count needed to pass the top-10 cut-off.

#### Scenario: Check passes with no new events
- **WHEN** `check` runs against a stack whose baseline was built from the original split
- **THEN** it prints PASS and exits 0

#### Scenario: Plan names the closest pair
- **WHEN** `plan` runs on the baseline data (no events in the ledger)
- **THEN** it reports rank 9 over rank 8 as the closest pair with an estimate near 18 ratings

#### Scenario: Re-running inject
- **WHEN** `inject` is run twice with the same arguments
- **THEN** the second run creates no new ledger entries and reports that the events already exist

#### Scenario: Dry run
- **WHEN** `inject --dry-run` is used
- **THEN** it lists the users and eventIds it would send and sends nothing

### Requirement: Cleanup of synthetic ratings
`scripts/purge_demo_ratings.py` SHALL remove the ledger events, `user_rated` documents and `user_history` documents of users in a given range, defaulting to a dry run that only prints counts, and SHALL refuse any range not inside 999,000,000–999,999,999. The documentation SHALL state that the ledger must be purged before a retrain handoff and describe the manual procedure for the `year=2026` partition of `curated_ratings`.

#### Scenario: Dry run
- **WHEN** the script runs without `--yes`
- **THEN** it prints how many documents it would delete from each collection and deletes nothing

#### Scenario: Range guard
- **WHEN** the range includes a real MovieLens user id such as 1
- **THEN** the script exits with an error and deletes nothing

#### Scenario: Purge removes the synthetic ratings from the statistics
- **WHEN** 20 synthetic users each rated a movie, they are purged, and the cache TTL has passed
- **THEN** `/debug/popularity` shows that movie's `newRatings` lower by 20 and its WR back to the value it had before the run
