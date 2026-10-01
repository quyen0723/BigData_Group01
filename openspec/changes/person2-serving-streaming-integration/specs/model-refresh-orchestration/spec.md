## ADDED Requirements

### Requirement: Retraining trigger
The orchestrator SHALL trigger a retraining request when the number of applied rating events since the last handoff reaches a configured minimum, on a configured schedule, or on explicit `--force`; it MUST NOT train or activate a model itself.

#### Scenario: Below threshold
- **WHEN** fewer applied events than the configured minimum exist since the last handoff and `--force` is not given
- **THEN** no handoff package is created and the orchestrator logs the current count and threshold

#### Scenario: Threshold reached
- **WHEN** the count of applied events since the last handoff reaches the minimum
- **THEN** a handoff package is created and the handoff watermark is advanced

### Requirement: Data handoff package for Person 1
Each retraining request SHALL produce a directory containing `delta_ratings.parquet` with the curated §2.1 schema holding the applied events in the handoff window, and a `manifest.json` recording request id, active version, proposed candidate version, window cutoff, row count, user and new-user counts, maximum event timestamp, the latest-wins deduplication rule and a checksum.

#### Scenario: Delta completeness
- **WHEN** a handoff package is created
- **THEN** the delta row count equals the number of ledger events in the window and the manifest checksum matches the delta file

### Requirement: Staged candidate import
A candidate returned by Person 1 SHALL be imported with its own `modelVersion` into the serving collections in staged state, registered in `model_registry` with status `staged`, and MUST NOT be served until activation.

#### Scenario: Candidate not served while staged
- **WHEN** candidate `v1.1.0` has been imported but not activated
- **THEN** API responses still report the previously active `modelVersion`

### Requirement: Promotion gate with independent verification
The promotion gate SHALL load the active and candidate models with `ALSModel.load()`, compute RMSE for both on the same fixed holdout, and PASS only if all criteria hold: candidate RMSE ≤ active RMSE × (1 + ε); candidate RMSE below the MovieMean test RMSE; candidate RMSE within [0.6, 1.1]; 100% of staged documents schema-valid with ranks 1..n and n ≤ 10; zero already-rated items against curated base plus delta; candidate user coverage ≥ active user coverage; candidate version greater than active with the same MAJOR and never used before. The gate SHALL write a machine-readable report for every run.

#### Scenario: Gate report
- **WHEN** the gate runs on any candidate
- **THEN** a report lists each criterion with measured value, threshold and PASS/FAIL, and it is stored in `model_registry` and as an evidence file

#### Scenario: Self-reported metrics not trusted
- **WHEN** the candidate `model_card.json` states an RMSE different from the gate's recomputation
- **THEN** the gate decides using the recomputed value and records both values in the report

### Requirement: Fail keeps current version
When any gate criterion fails, the active pointer in `serving_meta` MUST remain byte-for-byte unchanged and the candidate SHALL be marked `rejected`; a rejected version identifier MUST NOT be reused.

#### Scenario: Fail path preserves serving
- **WHEN** a deliberately degraded candidate fails the RMSE criterion
- **THEN** the `serving_meta` document before and after the gate is identical, API responses keep the old `modelVersion`, and the candidate status is `rejected`

### Requirement: Pass activates atomically
When all gate criteria pass, the orchestrator SHALL set the candidate to `active`, the previous version to `retired`, and switch `serving_meta` with a single-document update recording `previousVersion`, the artifact version map, activation time and gate report reference.

#### Scenario: Pass path switches version
- **WHEN** a candidate passes the gate
- **THEN** after the pointer cache TTL, all API responses report the candidate `modelVersion`, and enough-history users are served from the candidate's recommendations

### Requirement: Rollback and retention
The orchestrator SHALL provide a rollback command that restores `previousVersion` when its documents still exist, and a cleanup command that deletes documents of retired versions beyond the configured retention (default: keep active and previous).

#### Scenario: Rollback
- **WHEN** rollback is executed after a promotion
- **THEN** the pointer references the previous version and API responses report it again

#### Scenario: Rollback target missing
- **WHEN** rollback is requested but the previous version's documents were cleaned up
- **THEN** the command aborts without changing the pointer and reports why
