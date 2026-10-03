## ADDED Requirements

### Requirement: Baseline statistics from the training split
A loader SHALL compute, for every movie with at least one rating in the training split, the rating count `n0` and rating sum `sum0`, and store them in the `movie_stats` collection (`_id` = movieId) together with one metadata document (`_id` = `"_meta"`) holding the global training mean `C`, the cutoff, the number of ratings counted, the number of movies, the creation time and `ledgerSince` (null for a baseline built from the original split). The training split SHALL be the ratings with `timestamp` strictly below the cutoff recorded in `evidence/split_stats.csv`. The loader SHALL fail, writing nothing, when the number of ratings counted differs from `n_train` in that file or when the global mean differs from the recorded `C` at four decimals. After writing, the loader SHALL check that the `n0` values stored in Mongo add up to the ratings counted and that their sums give the same mean, and write `_meta` only if they do. Running it again SHALL replace the previous contents. `--ledger-since` without a time zone SHALL mean UTC.

#### Scenario: Baseline matches the offline split
- **WHEN** the loader runs on the bundle whose split has `cut_val = 1476348398` and `n_train = 22,399,368`
- **THEN** `movie_stats` holds one document per movie rated in that split, the metadata ratings count is 22,399,368 and `C` is 3.5287

#### Scenario: Streamed ratings are not part of the baseline
- **WHEN** `curated_ratings` also contains ratings appended by the streaming pipeline (timestamps after the cutoff)
- **THEN** none of them is counted in `n0` or `sum0`

#### Scenario: A wrong cutoff is refused
- **WHEN** the loader is given a cutoff that yields a rating count different from `n_train`
- **THEN** it exits with an error and `movie_stats` is unchanged

### Requirement: Live popularity is the baseline plus applied ledger events
The serving layer SHALL compute a movie's live statistics as `v = n0 + n_new` and `R = (sum0 + sum_new) / v`, where `n_new` and `sum_new` come from the ratings in the `rating_events` ledger, counting **one rating per (userId, movieId) pair, the one with the latest `timestamp` (then `ingestedAt`)**, and ignoring events whose `ingestedAt` is not after the baseline's `ledgerSince` when that is set. A movie absent from `movie_stats` SHALL start from `n0 = 0`, `sum0 = 0`. The streaming pipeline, the ledger schema and the rating API SHALL NOT change.

#### Scenario: A new rating moves the statistics
- **WHEN** a movie has `n0 = 12,776` and `R0 = 4.258` and the ledger holds one new 5-star event for it
- **THEN** its live `v` is 12,777 and its live `R` is `(12,776 × 4.258 + 5) / 12,777`

#### Scenario: The same user rates the same movie twice
- **WHEN** the ledger holds two events for one (user, movie) pair, 3 stars then 5 stars
- **THEN** only the 5-star rating is counted and `n_new` is 1

#### Scenario: A replayed event is counted once
- **WHEN** the streaming pipeline processes the same eventId twice
- **THEN** the ledger holds it once and `n_new` rises by 1, not 2

#### Scenario: Events already inside a rebuilt baseline
- **WHEN** the baseline's `ledgerSince` is T and an event has `ingestedAt` earlier than T
- **THEN** that event is not counted

### Requirement: Same formula and ordering as the offline artifact
The live ranking SHALL use `WR = v/(v+m)·R + m/(v+m)·C` with `m` from configuration (1000) and `C` from the baseline metadata, keep only movies with `v >= min_support` (100), and order by WR descending, then `v` descending, then movieId ascending. It SHALL return `top_n` entries (default 10), each with `score = WR` and `support = v`, in the shape the recommendation service already expects from the artifact.

#### Scenario: No events means the offline list
- **WHEN** the ledger holds no events newer than the baseline
- **THEN** the live top 10 has the same movieIds in the same order as `artifacts/popular_movies.json`, and each WR differs from the artifact's score by at most 0.0005

#### Scenario: Support filter uses the live count
- **WHEN** a movie has `n0 = 95` and five new ratings
- **THEN** it becomes eligible; with four new ratings it is not

#### Scenario: Ties are broken deterministically
- **WHEN** two movies have equal WR
- **THEN** the one with the larger `v` ranks first, and if that is equal too, the smaller movieId

#### Scenario: A low-support movie stays low
- **WHEN** a movie has `v = 173` and `R = 4.468` and 100 new 5-star ratings arrive
- **THEN** its live WR is about 3.77 and it is not in the top 10

### Requirement: Recommendations use the live list for the popularity source
When live popularity is enabled and available, `GET /recommendations/{userId}` SHALL take its popularity candidates (the only source for tier `0_history`, the padding source, and the popularity source of the other tiers) from the live ranking instead of the artifact. Tiers, routing, fusion, exclusion of rated movies, the new-movie source and the response shape SHALL otherwise be unchanged.

#### Scenario: A new user sees the live order
- **WHEN** a user with no history requests recommendations after enough 5-star ratings moved Seven Samurai above One Flew Over the Cuckoo's Nest
- **THEN** Seven Samurai appears before One Flew Over the Cuckoo's Nest in the response, all with source `popularity`

#### Scenario: Other tiers are unaffected
- **WHEN** a user with `enough_history` and an ALS document requests recommendations
- **THEN** the ALS and content results are the same as with live popularity disabled

### Requirement: Fall back to the artifact, never fail the request
The service SHALL use the artifact list when live popularity is disabled, when `movie_stats` has no metadata document or is empty, or when computing the live ranking fails and no result younger than 60 seconds exists. It SHALL log one warning per cause per minute and SHALL NOT return an error to the client because of it.

#### Scenario: Flag off
- **WHEN** `popularity.live` is false
- **THEN** the response is identical to what the artifact alone produces

#### Scenario: Baseline missing
- **WHEN** `movie_stats` is empty
- **THEN** `GET /recommendations/{userId}` answers 200 with the artifact list and the log has one warning

#### Scenario: Nothing is eligible
- **WHEN** no movie has `min_support` ratings (the setting is far too high)
- **THEN** the artifact list is used and one warning is logged; the response is never an empty list

#### Scenario: Ledger read fails
- **WHEN** reading the ledger raises an error and a live result from 20 seconds ago exists
- **THEN** that result is used; with no recent result the artifact list is used

### Requirement: Configuration
`configs/serving.yaml` SHALL provide a `popularity` block with `live` (boolean), `m` (default 1000), `min_support` (default 100), `top_n` (default 10, at most 50) and `cache_ttl_seconds` (default 2). When the block is absent, `live` SHALL be false so that an older configuration keeps the artifact behaviour. Invalid values SHALL stop the service at start with a clear message.

#### Scenario: Older configuration
- **WHEN** `configs/serving.yaml` has no `popularity` block
- **THEN** the service starts and serves the artifact list

#### Scenario: Invalid value
- **WHEN** `popularity.top_n` is 0 or `popularity.m` is negative
- **THEN** loading the configuration fails with a message naming the key

### Requirement: Cached computation
The ledger aggregation SHALL be cached for `cache_ttl_seconds` and shared by every request, whatever its `m` or `n`; the live ranking SHALL be cached per (`m`, with or without ledger events, `n`) for the same time, with a bounded number of cached combinations that never evicts the one `/recommendations` reads. Concurrent refreshes SHALL be collapsed into one computation, and a reader that already holds a recent result SHALL receive it instead of waiting for a refresh in progress. Baseline statistics SHALL be loaded into memory once and reloaded when the metadata `generatedAt` changes.

#### Scenario: Many requests, one computation
- **WHEN** 50 requests for tier-0 users arrive within one TTL window
- **THEN** the ledger aggregation runs once

#### Scenario: Different n and m, one aggregation
- **WHEN** within one TTL window requests ask for n = 10, n = 12, n = 50 and a preview with m = 0
- **THEN** the ledger aggregation runs once

#### Scenario: Debug traffic cannot push out the serving entry
- **WHEN** 60 different preview values of `m` are requested with a long TTL
- **THEN** the cached list that `/recommendations` reads is still there and the number of cached combinations stays at or below 32

#### Scenario: Baseline rebuilt
- **WHEN** the loader replaces `movie_stats` and the metadata `generatedAt` changes
- **THEN** the next refresh uses the new baseline without restarting the API
