## ADDED Requirements

### Requirement: Handoff window bounded by committed events
The retraining orchestrator SHALL build each handoff package from the ledger events whose `ingestedAt` is greater than the handoff watermark and not greater than the `lastRunAt` of the last committed micro-batch recorded in `pipeline_state.ratings_stream`, and SHALL set the new watermark and the manifest `windowEnd` to that same upper bound. It MUST NOT derive the watermark from the wall clock or from event timestamps. When no committed batch is recorded, no handoff package SHALL be created.

#### Scenario: Batch applied while the handoff is being built
- **WHEN** a micro-batch inserts its ledger documents after the handoff read `lastRunAt` and before the handoff finishes writing its package
- **THEN** none of that batch's events are in this package, and all of them are in the next package

#### Scenario: Partially inserted batch
- **WHEN** the handoff runs while a batch has inserted only part of its ledger documents and has not committed
- **THEN** no document of that batch is exported, so the rest of the batch is not lost by the new watermark

#### Scenario: Every committed event is exported exactly once
- **WHEN** two handoffs run one after another with rating events applied between them
- **THEN** the union of their delta files contains every committed event exactly once, and each delta row count equals the ledger count in its window

#### Scenario: Streaming never ran
- **WHEN** `pipeline_state.ratings_stream` does not exist
- **THEN** the orchestrator logs that nothing is committed and creates no package

### Requirement: Promotion gate holdout is deduplicated
The promotion gate SHALL collapse the holdout read from `curated_ratings` to one row per `(userId, movieId)`, keeping the rating of the row with the greatest `timestamp`, before computing any RMSE, so rows appended more than once by an at-least-once batch replay do not change the result.

#### Scenario: Replayed batch appended twice
- **WHEN** `curated_ratings` contains the same `(userId, movieId, rating, timestamp)` row twice inside the holdout window
- **THEN** the gate's RMSE equals the value computed with that row present once

#### Scenario: Historical holdout unchanged
- **WHEN** the holdout contains no repeated `(userId, movieId)` pair
- **THEN** the gate's RMSE for a given model equals the value computed without deduplication

### Requirement: Promotion gate fails closed without a holdout cut
When neither the candidate nor the active model card provides `split.cut_test`, the promotion gate SHALL mark G1, G2 and G3 as FAIL with a reason naming the missing cut, SHALL NOT compute RMSE on the full curated ratings, and SHALL still evaluate the remaining criteria and write its report.

#### Scenario: Both cards lack the cut
- **WHEN** the gate runs with two model cards that have no `split.cut_test`
- **THEN** G1–G3 are FAIL with a message about the missing `cut_test`, no RMSE is computed, the candidate is not promoted, and the report is still written

#### Scenario: One card has the cut
- **WHEN** only the active card has `split.cut_test`
- **THEN** the gate uses that value and evaluates normally
