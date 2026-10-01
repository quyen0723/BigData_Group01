## ADDED Requirements

### Requirement: Rating event transport
Rating events conforming to CONTRACTS.md §5 (`eventId`, `userId`, `movieId`, `rating`, `timestamp` in epoch seconds, `source`) SHALL be published to the Kafka topic `ratings.v1` with the record key set to `userId`, so events of one user keep their order within a partition.

#### Scenario: Produce and consume
- **WHEN** the producer simulator sends an event
- **THEN** the event is readable from `ratings.v1` with key equal to its `userId`, and the producer log records topic, partition and offset

### Requirement: Producer simulator
A producer simulator SHALL generate events for a scripted demo scenario, random replay from the catalog, deliberately invalid events and duplicate `eventId` resends, each selectable by command-line option.

#### Scenario: Scripted new-user scenario
- **WHEN** the simulator runs the demo scenario for a new userId
- **THEN** it emits the configured ordered list of ratings for that user with fresh UUID4 `eventId`s

### Requirement: Raw event storage
Every consumed Kafka record SHALL be persisted unmodified with its partition, offset and ingest date to a raw Parquet store through a Structured Streaming file sink with its own checkpoint, independent of validation outcome.

#### Scenario: Raw copy of an invalid event
- **WHEN** a malformed event is produced
- **THEN** it appears in raw event storage and is not lost, even though it is rejected downstream

### Requirement: Validation and quarantine
The validated stream SHALL accept only events whose JSON parses, whose `eventId` is non-empty, whose `userId > 0`, whose `movieId` exists in `curated_movies`, whose `rating` is in {0.5, 1.0, …, 5.0} and whose `timestamp` is positive and not more than one day in the future; rejected events SHALL be written to a quarantine store with the first failing rule as `reason`, and MUST NOT change curated data or serving state.

#### Scenario: Invalid rating value
- **WHEN** an event with `rating = 7.0` is produced
- **THEN** it is written to quarantine with a rating-range reason, and `curated_ratings`, `user_history` and `user_rated` are unchanged

#### Scenario: Unknown movie
- **WHEN** an event references a `movieId` absent from `curated_movies`
- **THEN** it is quarantined with an unknown-movie reason

### Requirement: Event deduplication and idempotent effects
The pipeline SHALL deduplicate by `eventId` using an event-time watermark with state-bounded deduplication and SHALL additionally drop events whose `eventId` already exists in the `rating_events` ledger; applying a micro-batch more than once MUST leave `user_history`, `user_rated` and the ledger in the same state as applying it once.

#### Scenario: Duplicate eventId resent
- **WHEN** the same event (same `eventId`) is produced twice, including after the watermark has passed
- **THEN** `interaction_count` and `recent_movieIds` reflect the event exactly once and the ledger holds a single document for that `eventId`

#### Scenario: Batch replay after crash
- **WHEN** the streaming container is killed after serving-state updates but before the batch commit, and then restarted
- **THEN** the replayed batch leaves `user_history` and `user_rated` identical to a single application, and processing resumes from the checkpoint

### Requirement: Curated Parquet append without hiding historical data
Validated events SHALL be appended to the curated ratings dataset with the §2.1 columns (`userId`, `movieId`, `rating`, `timestamp`, `rating_ts`) partitioned by `year`, using a batch writer inside `foreachBatch`; the streaming file sink MUST NOT write to the curated ratings path, so no `_spark_metadata` directory is created there.

#### Scenario: Historical rows remain visible
- **WHEN** a batch read of `curated_ratings` is performed after streaming has appended N valid events
- **THEN** the row count equals 32,000,204 plus the appended rows, and no `_spark_metadata` directory exists under the curated ratings path

#### Scenario: Schema compatibility
- **WHEN** the appended data is read together with historical data
- **THEN** the unified schema has the same column names and types as the historical curated ratings

### Requirement: Immediate serving-state update
For each newly applied event, the pipeline SHALL upsert `user_rated` with latest-timestamp-wins semantics and SHALL update the user's `user_history`: `interaction_count` recomputed as the number of distinct rated movies, the movie moved to the front of `recent_movieIds` (capped at R), moved to the front of `positive_movieIds` when rating ≥ 4.0 or removed from it otherwise (capped at P), and `lastUpdated` set to the maximum event time; unknown users SHALL be created.

#### Scenario: Request after rating sees new history
- **WHEN** a new user submits their first valid rating and then requests recommendations
- **THEN** `interaction_count` is 1, the rated movie is first in `recent_movieIds`, and the API routes the user as `few_history` (given T > 1)

#### Scenario: Re-rating a movie
- **WHEN** a user submits a new rating for a movie they already rated
- **THEN** `interaction_count` is unchanged and `user_rated` holds the rating with the later timestamp

### Requirement: Checkpointing and progress evidence
Every streaming query SHALL use a dedicated checkpoint location, and the pipeline SHALL log per-batch progress (input and processed rows per second, batch duration, watermark) as evidence.

#### Scenario: Restart continues from offsets
- **WHEN** the streaming job is stopped and restarted
- **THEN** it resumes from the last committed Kafka offsets without reprocessing committed batches, as shown by the progress log
