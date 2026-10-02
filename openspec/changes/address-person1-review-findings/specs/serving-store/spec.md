## ADDED Requirements

### Requirement: Bootstrap does not replace an active pointer
The bootstrap registry loader SHALL refuse to write `serving_meta.active` when an active pointer already exists for a different `modelVersion`, SHALL exit with a non-zero status before running its checks or writing `model_registry`, and SHALL name `promotion_gate` and `manage_versions` as the way to change the active version. Re-running it for the version that is already active SHALL be allowed. Documentation MUST NOT describe the bootstrap step as safe to rerun after streaming has applied events or after another version has been loaded.

#### Scenario: Another version is active
- **WHEN** `serving_meta.active` points to `v1.1.0` and the loader runs with `--version v1.0.0`
- **THEN** it exits non-zero with a message pointing to `promotion_gate` and `manage_versions`, and `serving_meta` and `model_registry` are unchanged

#### Scenario: First bootstrap
- **WHEN** no `serving_meta.active` document exists and all checks pass
- **THEN** the pointer is written for the given version as before

#### Scenario: Same version again
- **WHEN** `serving_meta.active` already points to the given version
- **THEN** the loader is allowed to run and does not change the pointer to another version
