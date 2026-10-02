## ADDED Requirements

### Requirement: Reproducible containerized runtime
The system SHALL provide a Docker Compose stack that starts MongoDB (single node), Kafka (KRaft, single broker), a Spark 3.5.x runtime whose PySpark version matches the version pinned by Person 1 (`pyspark==3.5.7`), and the Recommendation API with a single documented command.

#### Scenario: Clean start
- **WHEN** a reviewer with Docker installed runs the documented start command on a clean checkout that has the `movielens32m/` bundle in place
- **THEN** all four services report healthy and the API health endpoint responds successfully

#### Scenario: Version evidence
- **WHEN** the stack is built for the first time
- **THEN** the exact image tags, Spark/PySpark version, Spark package coordinates (Kafka and MongoDB connectors) and Python package versions are recorded in `evidence/p2_env_versions.txt`

### Requirement: Configuration without hardcoded paths or credentials
All paths, collection names, topic names and tunable parameters SHALL be read from `configs/serving.yaml` and `configs/streaming.yaml`, and connection strings or credentials MUST be supplied through environment variables with only placeholder values committed (`.env.example`).

#### Scenario: No secrets in source
- **WHEN** the repository is searched for connection strings or credentials
- **THEN** no real credential values are found in committed files, and every service reads its connection settings from environment variables

#### Scenario: Tunable parameter change
- **WHEN** an operator changes the few/enough threshold `T` in `configs/serving.yaml` and restarts the API
- **THEN** routing uses the new value without any source-code change

### Requirement: Local data bundle mount
The runtime SHALL mount the gitignored `movielens32m/` bundle (curated Parquet, serving artifacts, models, candidates, stream directories) into the Spark and API containers at a fixed path, and SHALL create the stream subdirectories (`raw_events`, `quarantine`, `checkpoints`, `handoff`) if they are missing.

#### Scenario: Missing bundle
- **WHEN** the start command runs and the `movielens32m/` bundle or a required artifact file is missing
- **THEN** the bootstrap step fails fast with a message naming the missing path and pointing to the Drive download instructions

### Requirement: Documented run sequence
The README SHALL contain the exact command sequence for Person 2 components, from environment start to a verified recommendation response, streaming demo and promotion demo.

#### Scenario: Reviewer follows README
- **WHEN** a reviewer executes the README run sequence in order
- **THEN** each step produces the output or evidence file that the README names for that step
