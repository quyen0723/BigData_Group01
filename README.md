Hybrid recommender (Movie Mean / Popularity / Content-Based / ALS) with history-based
switching, built on PySpark ETL → Curated Parquet → Spark ML → MongoDB serving.
See `docs/` for the PRD and Architecture Deep Dive.

> **M2 package (serving artifacts + ALS model, Person 2 consume):**
> https://drive.google.com/drive/folders/1nruGnD_DvSZqAfhwpC7tk_Va6pyUw3yF?usp=sharing
> Hướng dẫn: `notebooks/colab/README_COLAB_SETUP.md` §5 (mongoimport, user_history seed, ALSModel.load, version rule).

## Roles (per Project Management Tracker)
- **Person 1 (Quyên)**: Data → Modeling → Evaluation → Serving Artifacts
- **Person 2**: MongoDB → API → Routing → Streaming → Serving Integration

## Repository layout
```
configs/          Spark/MongoDB/app configuration (YAML)
contracts/        Frozen data + serving artifact contracts (WBS 0.2)
data/raw/         MovieLens 32M CSV (not committed — download)
data/curated/     Curated Parquet (not committed)
movielens32m/     M2 handoff bundle from Drive (not committed — see below)
src/etl/          PySpark ingestion, cleaning, joins (WBS 1.1–1.3, Person 1)
src/analytics/    Spark SQL analytics + MapReduce (WBS 2.1–2.2, Person 1)
src/modeling/     Split, baselines, content-based, ALS, evaluation (WBS 3.x, 6.x, Person 1)
src/loaders/      Mongo serving-store loaders: indexes, movies, user_rated/history, artifacts (Person 2)
src/serving/      Recommendation pipeline: router, fusion, exclusion, history, repository (Person 2)
src/streaming/    Kafka producer + Structured Streaming pipeline + event validation (Person 2)
src/api/          Recommendation API (FastAPI) (Person 2)
src/orchestration/ Retrain trigger, stage candidate, promotion gate, rollback/cleanup (Person 2)
docker/           Docker Compose stack (mongo, kafka, spark, api) (Person 2)
tests/unit/       Pytest suite for the serving/streaming logic (Person 2)
notebooks/colab/  Colab notebooks for model training (ALS, evaluation, artifacts)
artifacts/        Serving artifacts: popularity_topn, similar_movies, als_topn
evidence/         Evidence per task (schemas, counts, plans, timing tables) — p2_* = Person 2
docs/             PRD, Architecture, SERVING_ARCHITECTURE (Mermaid), DEPLOYMENT_DESIGN
openspec/changes/person2-serving-streaming-integration/  Proposal/design/specs/tasks for Person 2's scope
PLAN_Person1.md   Person 1 step-by-step plan (in → out → KILL → Q)
CHECKLIST_Person1.md  Progress tracker — update after EVERY step
tasks.md          Team task log
```

## Environment
- Python 3.12, PySpark (version pinned in `configs/requirements.txt` — filled at B0.1 verify)
- Local PySpark for ETL/analytics; **Google Colab** for model training (ALS, evaluation)
- **Docker Compose** for serving/streaming (MongoDB, Kafka, Spark, API — Person 2)

## Getting started — Person 1 (offline pipeline)
```bash
# 1. Download MovieLens 32M into data/raw/
#    https://grouplens.org/datasets/movielens/  (ml-latest-32m.zip)
# 2. Install dependencies
pip install -r configs/requirements.txt
# 3. Run skeleton check
python src/etl/verify_skeleton.py
```

## Getting started — Person 2 (serving, streaming, retraining)

Requires Docker Desktop, ≥16 GB RAM allocated to it (WSL2 on Windows: `.wslconfig`
`memory=16GB`, then `wsl --shutdown` and reopen Docker Desktop — 8 GB was measured
insufficient for the 32M-row loader job).

```bash
# 0. Download the M2 bundle (curated/, artifacts/, models/) from Drive into ./movielens32m
#    https://drive.google.com/drive/folders/1nruGnD_DvSZqAfhwpC7tk_Va6pyUw3yF
python scripts/bootstrap_stream_dirs.py        # fail-fasts if any required file is missing

# 1. Start the stack (docker/docker-compose.yml hardcodes the intra-network
#    connection strings for course-scope simplicity; .env.example documents the
#    same values for any host-side script/tool you point at the exposed ports)
docker compose -f docker/docker-compose.yml up -d --build

# 2. Load MongoDB serving store ONCE, in this order, on a fresh store. Not a "rerun anytime" step:
#    - build_movies replaces every movie by _id; build_user_state uses plain inserts (do not
#      rerun it on a loaded store); load_artifacts deletes and reloads that version's documents;
#    - bootstrap_registry (last line) is the first-load check. It refuses to replace an active
#      pointer that names another version, and its exact document counts (movies, user_rated,
#      user_history, popular_movies) stop matching once streaming has applied events or a second
#      version was loaded, so a later rerun fails check G4 and writes nothing.
#    To change the active version use orchestration.promotion_gate / manage_versions (step 5).
#    To start over, empty the Mongo volume first.
docker compose -f docker/docker-compose.yml exec spark python -m loaders.create_indexes
docker compose -f docker/docker-compose.yml exec spark python -m loaders.build_movies
docker compose -f docker/docker-compose.yml exec spark python -m loaders.build_user_state
docker compose -f docker/docker-compose.yml exec spark python -m loaders.load_artifacts --artifact popular  --version v1.0.0
docker compose -f docker/docker-compose.yml exec spark python -m loaders.load_artifacts --artifact similar  --version v1.0.0
docker compose -f docker/docker-compose.yml exec spark python -m loaders.load_artifacts --artifact als_topn --version v1.0.0
docker compose -f docker/docker-compose.yml exec spark python -m loaders.bootstrap_registry --version v1.0.0
# expected on a fresh store: 7/7 gate checks PASS, "v1.0.0 is now the active serving version"

# 3. Try the API (host port 8088 — not 8000, which Windows dev tools like Laragon often occupy)
curl http://127.0.0.1:8088/recommendations/1?k=5
# Demo UI (needs api.demo_enabled: true in configs/serving.yaml, then restart `api`):
#   http://127.0.0.1:8088/app    user app: pick a demo persona, rate movies
#   http://127.0.0.1:8088/admin  admin console (also /demo): case tests, demo movies, model lifecycle
# Personas are demo accounts mapped to real MovieLens users; there is no authentication.
# The pages are a React build (web/, built into the `api` image by `docker compose up -d --build api`).
# api.ui in configs/serving.yaml picks what /app, /admin, /demo serve: "react" (default) or "legacy"
# (the old static pages, always reachable at /legacy/app and /legacy/admin). Frontend dev, scripts
# and checks: web/README.md.

# 4. The streaming pipeline is the `streaming` service: it already started with step 1 and
#    restarts by itself after a Docker Desktop restart or a crash (restart: unless-stopped).
#    Do NOT also run `python -m streaming.pipeline` by hand: it is a singleton (one checkpoint).
#    Note: on a brand-new empty Mongo volume it cannot start until step 2 has loaded `movies`,
#    so it may restart a few times first (not tried on an empty volume).
docker compose -f docker/docker-compose.yml ps streaming          # should say healthy
docker compose -f docker/docker-compose.yml logs -f streaming     # serve_batch[N]: committed ...
# simulate a rating (applied after ~15-45 s, measured):
docker compose -f docker/docker-compose.yml exec spark \
  python -m streaming.producer --mode scenario --user-id 300001 --movie-ids 296,318,858 --bootstrap-servers kafka:9092
curl http://127.0.0.1:8088/recommendations/300001   # tier should now be few_history

# 5. Retraining orchestration (needs a candidate from Person 1 — see
#    openspec/changes/person2-serving-streaming-integration/design.md D-12)
docker compose -f docker/docker-compose.yml exec spark python -m orchestration.retrain_trigger --force
docker compose -f docker/docker-compose.yml exec spark python -m orchestration.stage_candidate --version v1.1.0 --candidate-dir /data/candidates/v1.1.0
docker compose -f docker/docker-compose.yml exec spark python -m orchestration.promotion_gate --version v1.1.0
docker compose -f docker/docker-compose.yml exec spark python -m orchestration.manage_versions rollback   # if needed
```

**Tests** (no Docker needed — pure Python + a fake in-memory repository):
```bash
python -m venv .venv-serving && .venv-serving/Scripts/pip install -r configs/requirements_serving.txt pytest
.venv-serving/Scripts/python -m pytest tests/ -v   # 163 tests
```

**Evidence** for every step above is in `evidence/p2_*` (counts, gate reports, test matrix,
load test) — see `openspec/changes/person2-serving-streaming-integration/tasks.md` for the
full checklist with what has and hasn't been verified against a live stack.

## Conventions
- Config via `configs/*.yaml`, no hardcoded paths in source.
- Data contracts are FROZEN in `contracts/CONTRACTS.md` (WBS 0.2). Any artifact
  written to MongoDB MUST match the frozen schema exactly.
- Definition of Done (tracker rule 1): code runs + output correct + evidence exists
  + downstream can consume. Update `CHECKLIST_Person1.md` immediately after each step.
- Commit message: `<type>: <subject>` (English, short).
- Backup policy: git is the primary backup (`git tag` at each milestone M0–M8);
  important file edits also keep `file.YYYYMMDD_HHMMSS.bak` per workspace rules.
