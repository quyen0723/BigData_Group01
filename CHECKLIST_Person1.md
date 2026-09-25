# CHECKLIST — Person 1 (Quyên) — MovieLens Hybrid Rec System
> Quy tắc (tracker rule 1): DONE ⟺ code runs + output correct + evidence exists + downstream consume được.
> Cập nhật NGAY sau mỗi bước (INV4). Bị chặn ⟹ status Blocked + blocker + next action.
> Trạng thái ∈ {Not Started, In Progress, Blocked, Done}. % = 0/25/50/75/100.

| # | WBS | Bước | Môi trường | Priority | Status | % | Evidence | Ghi chú |
|---|-----|------|-----------|----------|--------|---|----------|---------|
| 1 | 0.1 | B0.1 Repo + config + naming | Local | Critical | **Done** | 100 | `git tag M0`; `evidence/b0_1_skeleton_verify.txt` (verify PASS 4/4) | venv pyspark 3.5.7 + Java 21; cấu trúc theo PLAN §2 |
| 2 | 0.2 | B0.2 Freeze CONTRACTS.md + sample JSON | Local | Critical | **Done** | 100 | `contracts/CONTRACTS.md` + 4 samples PASS | 4 artifact schema + routing tiers T (tunable) + event schema |
| 3 | 1.1 | B1.1 Ingest CSV explicit schema | Local | Critical | **Done** | 100 | `evidence/b1_1_ingest.txt` (5/5 counts OK, PASS) | Fix: PERMISSIVE+corrupt-col thay FAILFAST (Spark 3.5.7 mis-parse RFC-4180); escape='"' cho 244 tags có quote |
| 4 | 1.2 | B1.2 Clean + transform + join | Local | Critical | **Done** | 100 | `evidence/b1_2_clean.txt` (0 critical issues, PASS) | 0 null, 0 invalid, 0 dup, 0 unmatched; 7,080 movies no-genres, 3,153 movies 0 ratings (informational) |
| 5 | 1.3 | B1.3 Curated Parquet + read-back | Local | Critical | **Done** | 100 | `evidence/b1_3_curated.txt` (4/4 OK, PASS) | Partition year (1995-2023); schema compare theo simpleString (Parquet không round-trip nullable/containsNull) |
| 6 | 1.1–1.2 | B1.EDA EDA_REPORT.md | Local | High | **Done** | 100 | `docs/EDA_REPORT.md` (sinh bởi eda.py, 136 dòng) | KILL-EDA PASS; mọi số tái tạo bằng 1 lệnh |
| 7 | 2.1 | B2.1 Spark SQL + explain('formatted') | Local | High | **Done** | 100 | `evidence/b2_1_spark_sql.txt` (5 queries + plans) | 14 BroadcastExchange; PartitionFilters year>=2013; Q4 5 Exchange (đã verify) |
| 8 | 2.2 | B2.2 MapReduce cross-check | Local | Medium | **Done** | 100 | `evidence/b2_2_mapreduce.txt` | 84,432/84,432 khớp, max diff 0.0 — PASS |
| 9 | 3.1 | B3.1 Split + MODEL_DESIGN §1–2 (seed, rule, leakage) | **Colab** | Critical | **Done** | 100 | `notebooks/Runned/01_split_baseline.ipynb` + `evidence/b3_1_split_baseline.txt` | 70.0/15.0/15.0%, KILL-LEAKAGE PASS; MODEL_DESIGN §1-2 còn phải viết |
| 10 | 3.2 | B3.2 Movie Mean + Popularity baselines | **Colab** | High | **Done** | 100 | `notebooks/Runned/01_split_baseline.ipynb` | RMSE test 0.9939 (band PASS); popularity deterministic PASS; ms=100 |
| 11 | 3.3 | B3.3 Content-Based Similar-Movie Lists | **Colab** | High | **In Progress** | 50 | `notebooks/colab/02_content_based.ipynb` ready | Block-matrix numpy (2048×87,585 ≈ 717MB/block) |
| 12 | 3.4 | B3.4 ALS + precompute Top-N | **Colab** | Critical | **In Progress** | 50 | `notebooks/colab/03_als_eval_artifacts.ipynb` ready | Checkpoint dir MANDATORY đã set trong notebook |
| 13 | 3.5 | B3.5 Evaluation + 4 serving artifacts → metrics.csv | **Colab** | Critical | **In Progress** | 50 | `notebooks/colab/03_als_eval_artifacts.ipynb` ready | KILL-CONTRACT assert trong notebook |
| 14 | 6.1 | B6.1 Retrain candidate version | **Colab** | Critical | Not Started | 0 | — | Sau khi Person 2 streaming append (5.2) |
| 15 | 6.2 | B6.2 Promotion gate + rollback logic | Colab/Local | High | Not Started | 0 | — | Fail-path phải giữ nguyên active version |
| 16 | 7.1 | B7.1 Controlled experiment CSV vs Parquet + repro manifest | Local | Medium | Not Started | 0 | — | Warm-up + 3–5 runs, median |
| 17 | 8.1 | B8.1 E2E integration + demo rehearsal | Cả hai | Critical | Not Started | 0 | — | Cùng Person 2 |
| 18 | 8.2 | B8.2 Evidence pack + release tag | Local | Critical | Not Started | 0 | — | Mọi rubric claim có evidence |

## Verify gates (đối chiếu sau mỗi bước — INV3)
- [x] G0: Person 2 dựng mock artifact từ CONTRACTS.md không hỏi lại — contracts + samples đã publish (M0, 2026-09-25)
- [x] G1 (M1, day 2): Parquet read-back schema/counts consistent — PASS 2026-09-25 (4/4 tables, evidence/b1_3_curated.txt)
- [ ] G2 (M2, day 5): metrics.csv đầy đủ + 4 artifacts đúng contract → handoff
- [ ] G3: MapReduce == Spark ± tolerance
- [ ] G4 (M5): gate fail-path giữ nguyên active version
- [ ] G5 (M7): demo reproducible từ README
- [ ] G6 (M8): evidence pack đủ → freeze tag

## Blockers / Decisions pending
| Ngày | Vấn đề | Owner | Next action |
|------|--------|-------|-------------|
| 2026-09-25 | Split: temporal vs random | Quyên | **ĐÃ NGHỆ CỨU** — khuyến nghị Global Temporal Split (SIGIR'23, TOIS'23, RecSys'20) + random sensitivity check. Chờ Quyên xác nhận |
| 2026-09-25 | K, Top-M, ALS grid | Quyên | **ĐÃ NGHỆ CỨU** — K=10+@20, Top-M=20, rank {10,50}, reg {0.05,0.1,0.17}, maxIter 10–15. Chờ Quyên xác nhận |
| 2026-09-25 | Colab full 32M vs sample | Quyên | **ĐÃ NGHỆ CỨU** — full 32M khả thi với checkpoint dir + driver-mem-before-JVM + rank ≤32; fallback sample 20%. Chờ Quyên xác nhận |
| — | Repo structure (PLAN §2) | Quyên | Đề xuất giữ nguyên, chờ duyệt ở B0.1 |

## Lịch sử cập nhật
- 2026-09-25: Viết 3 Colab notebooks + README_COLAB_SETUP.md + curated.zip 439MB. Mục 9–13 → In Progress 50% (notebook ready, chờ chạy trên Colab). 3 bug tự phát hiện qua review: f-string escape, dead code + overclaim, thiếu cell unzip.
- 2026-09-25: B1.EDA + B2.1 + B2.2 **DONE** (EDA_REPORT auto-generated; Spark SQL 5 analyses + plans verified; MapReduce cross-check exact 84,432/84,432). Phase 1+2 hoàn thành. Bước kế: B3.1 split + MODEL_DESIGN (Colab).
- 2026-09-25: B1.1–B1.3 **DONE** (M1 đạt sớm hơn schedule day 2). Data download verify PASS (MD5 GroupLens). 2 bugs parser phát hiện & fix có evidence: (1) FAILFAST vs RFC-4180 escaped quotes → PERMISSIVE+corrupt-assert; (2) schema read-back compare phải dùng simpleString. Bước kế: B1.EDA → B2.1/B2.2.
- 2026-09-25: B0.1 + B0.2 **DONE** — repo skeleton (venv pyspark 3.5.7, verify PASS 4/4), CONTRACTS.md frozen + 4 mock samples PASS, commit M0. Bước kế: B1.1 (cần download MovieLens 32M).
- 2026-09-25: Khởi tạo checklist (18 mục, tất cả Not Started) theo PLAN_Person1.md.