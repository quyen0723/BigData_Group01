## ADDED Requirements

### Requirement: Contract collections
The serving store SHALL hold the four contract collections `popular_movies`, `similar_movies`, `user_recommendations` and `user_history`, with document schemas exactly as defined in CONTRACTS.md §3.1–§3.4; the file `als_topn.json` MUST be loaded into the collection `user_recommendations`.

#### Scenario: Schema conformance after load
- **WHEN** artifacts of version `v1.0.0` are loaded
- **THEN** every document in the three artifact collections has exactly the contract fields, carries `modelVersion = "v1.0.0"` and `generatedAt`, and list items are sorted by rank ascending starting at 1

#### Scenario: Collection naming
- **WHEN** the ALS Top-N artifact is loaded
- **THEN** its documents are stored in `user_recommendations` and no collection named `als_topn` exists

### Requirement: Additive supporting collections
The serving store SHALL provide the additive collections `movies`, `user_rated`, `rating_events`, `serving_meta`, `model_registry` and `pipeline_state` without altering any contract document schema.

#### Scenario: Movie metadata available
- **WHEN** `movies` is built from `curated_movies`
- **THEN** it contains 87,585 documents keyed by `movieId` with `title`, `genres` and a rating `support` count

#### Scenario: Exact rated set available
- **WHEN** `user_rated` is built from `user_history_seed.parquet`
- **THEN** it contains one document per distinct (userId, movieId) pair, 32,000,204 in total, with a unique index on (userId, movieId)

### Requirement: Batch loading without mongoimport array limits
Serving artifacts SHALL be loaded with a Spark or batch driver that handles the full file sizes (`als_topn.json` 94 MB, `similar_movies.json` 82 MB) and both JSON shapes (top-level array and single object); loading MUST be idempotent per `modelVersion`.

#### Scenario: Single-object popularity file
- **WHEN** `popular_movies.json`, which is a single JSON object, is loaded
- **THEN** exactly one document for `scope = "global"` and that `modelVersion` exists

#### Scenario: Re-running a load
- **WHEN** the loader is run twice for the same version
- **THEN** document counts for that version are identical after both runs and no duplicate-key errors surface to the operator

#### Scenario: Version mismatch
- **WHEN** the loader is invoked with `--version v1.1.0` on a file whose documents carry a different `modelVersion`
- **THEN** the load aborts before writing and reports the mismatch

### Requirement: User history aggregation
The system SHALL build one `user_history` document per user by aggregating `user_history_seed.parquet` (never inserting raw rows), where `interaction_count` is the number of distinct movies rated, `recent_movieIds` holds at most R most recent movieIds by `rating_ts` (tie-break movieId), `positive_movieIds` holds at most P most recent movieIds with rating ≥ 4.0, and `lastUpdated` is the latest `rating_ts`.

#### Scenario: Aggregate reconciliation
- **WHEN** `user_history` is built from the seed
- **THEN** it contains 200,948 documents, the sum of `interaction_count` equals 32,000,204, the minimum equals 20 and the maximum equals 33,332

#### Scenario: Bounded arrays
- **WHEN** any `user_history` document is read
- **THEN** `recent_movieIds` has at most R elements and `positive_movieIds` has at most P elements

### Requirement: Access-pattern indexes
The serving store SHALL create unique indexes `(scope, modelVersion)` on `popular_movies`, `(movieId, modelVersion)` on `similar_movies`, `(userId, modelVersion)` on `user_recommendations`, `userId` on `user_history` and `(userId, movieId)` on `user_rated`; index creation MUST be idempotent.

#### Scenario: Point lookups use indexes
- **WHEN** `explain()` is run for the user recommendation lookup, the similar-movie `$in` lookup and the rated-set `$in` lookup
- **THEN** each plan uses an index scan (IXSCAN) and the rated-set lookup is a covered query, and the plans are saved as evidence

### Requirement: Versioned artifacts with an atomic active pointer
Artifact documents SHALL be versioned by `modelVersion`; the single document `serving_meta{_id:"active"}` SHALL record the active release `modelVersion`, the per-collection artifact version map and `previousVersion`; activation and rollback MUST each be a single-document update.

#### Scenario: Staged version is invisible
- **WHEN** documents of a candidate version are loaded while the pointer references `v1.0.0`
- **THEN** no API response contains candidate recommendations or the candidate `modelVersion`

#### Scenario: Activation switch
- **WHEN** the pointer is updated to a new version
- **THEN** subsequent requests (after the pointer cache TTL) are served entirely from the new version map, and no single response mixes versions

### Requirement: Read-back evidence
After every load, the system SHALL verify document counts against the source artifacts and run sample read-back queries per access pattern, saving the results as evidence.

#### Scenario: Count reconciliation
- **WHEN** the `v1.0.0` bootstrap load finishes
- **THEN** the evidence file shows `user_recommendations` = 154,608, `similar_movies` equal to the source document count, `popular_movies` = 1, `movies` = 87,585, `user_history` = 200,948 and `user_rated` = 32,000,204 for that version, each marked PASS or FAIL
