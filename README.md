Hybrid recommender (Movie Mean / Popularity / Content-Based / ALS) with history-based
switching, built on PySpark ETL → Curated Parquet → Spark ML → MongoDB serving.
See `docs/` for the PRD and Architecture Deep Dive.

## Roles (per Project Management Tracker)
- **Person 1 (Quyên)**: Data → Modeling → Evaluation → Serving Artifacts
- **Person 2**: MongoDB → API → Routing → Streaming → Serving Integration

## Repository layout
```
configs/          Spark/MongoDB/app configuration (YAML)
contracts/        Frozen data + serving artifact contracts (WBS 0.2)
data/raw/         MovieLens 32M CSV (not committed — download)
data/curated/     Curated Parquet (not committed)
src/etl/          PySpark ingestion, cleaning, joins (WBS 1.1–1.3)
src/analytics/    Spark SQL analytics + MapReduce (WBS 2.1–2.2)
src/modeling/     Split, baselines, content-based, ALS, evaluation (WBS 3.x, 6.x)
notebooks/colab/  Colab notebooks for model training (ALS, evaluation, artifacts)
artifacts/        Serving artifacts: popularity_topn, similar_movies, als_topn
evidence/         Evidence per task (schemas, counts, plans, timing tables)
docs/             PRD, Architecture, project management tracker
PLAN_Person1.md   Person 1 step-by-step plan (in → out → KILL → Q)
CHECKLIST_Person1.md  Progress tracker — update after EVERY step
tasks.md          Team task log
```

## Environment
- Python 3.12, PySpark (version pinned in `configs/requirements.txt` — filled at B0.1 verify)
- Local PySpark for ETL/analytics; **Google Colab** for model training (ALS, evaluation)
- MongoDB for serving (Person 2)

## Getting started
```bash
# 1. Download MovieLens 32M into data/raw/
#    https://grouplens.org/datasets/movielens/  (ml-latest-32m.zip)
# 2. Install dependencies
pip install -r configs/requirements.txt
# 3. Run skeleton check
python src/etl/verify_skeleton.py
```

## Conventions
- Config via `configs/*.yaml`, no hardcoded paths in source.
- Data contracts are FROZEN in `contracts/CONTRACTS.md` (WBS 0.2). Any artifact
  written to MongoDB MUST match the frozen schema exactly.
- Definition of Done (tracker rule 1): code runs + output correct + evidence exists
  + downstream can consume. Update `CHECKLIST_Person1.md` immediately after each step.
- Commit message: `<type>: <subject>` (English, short).
- Backup policy: git is the primary backup (`git tag` at each milestone M0–M8);
  important file edits also keep `file.YYYYMMDD_HHMMSS.bak` per workspace rules.
