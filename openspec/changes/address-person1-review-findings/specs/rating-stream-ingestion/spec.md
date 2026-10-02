## ADDED Requirements

### Requirement: Batch guard bound to the checkpoint that wrote it
The pipeline SHALL record, together with `lastBatchId` in `pipeline_state.ratings_stream`, the stream identity read from the checkpoint's `metadata` file, and SHALL skip a micro-batch as already committed only when the recorded identity equals the current one and `batchId <= lastBatchId`. When the identities differ, the pipeline MUST log a warning that the checkpoint changed, reset `lastBatchId`, and process the batch, relying on the `rating_events` ledger for idempotency. When the current identity cannot be read, the pipeline MUST process every batch and log a warning once. A state document without a recorded identity MUST NOT cause a skip: the batch is processed and the identity is recorded when it commits.

#### Scenario: A skipped batch is still read
- **WHEN** the guard decides to skip a batch
- **THEN** the batch's rows have already been read, so the deduplication state store of the stream advances with the offset log, and the next batch starts normally instead of failing on a missing state file

#### Scenario: Same checkpoint, batch already committed
- **WHEN** a batch with `batchId <= lastBatchId` is delivered and the recorded stream identity equals the current one
- **THEN** the batch is skipped, the log line says it was already committed and skipped, and nothing is written

#### Scenario: Checkpoint directory lost while Mongo survives
- **WHEN** the streaming checkpoint is deleted, the pipeline restarts with batch ids from 0, and `pipeline_state.ratings_stream.lastBatchId` is 43
- **THEN** the first batch logs a "checkpoint changed" warning, `lastBatchId` is reset, and a new rating produced afterwards is applied and its `GET /ratings/{eventId}` becomes `applied`

#### Scenario: Replay after the checkpoint was lost does not duplicate effects
- **WHEN** the pipeline reprocesses events that are already in the ledger after a checkpoint change
- **THEN** `user_rated`, `user_history`, the ledger and `curated_ratings` are unchanged by those events

#### Scenario: Identity cannot be read
- **WHEN** the checkpoint `metadata` file is missing or unreadable
- **THEN** no batch is skipped, one warning is logged, and the ledger dedup still prevents duplicate effects

#### Scenario: State written before this change
- **WHEN** `ratings_stream` has `lastBatchId` but no recorded stream identity
- **THEN** the batch is processed (not skipped), a warning says the stream identity was not recorded, and the identity is stored when the batch commits
