# CHECKLIST — Person 1 (Quyên) — MovieLens Hybrid Rec System
> Quy tắc (tracker rule 1): DONE ⟺ code runs + output correct + evidence exists + downstream consume được.
> Cập nhật NGAY sau mỗi bước (INV4). Bị chặn ⟹ status Blocked + blocker + next action.
> Trạng thái ∈ {Not Started, In Progress, Blocked, Done}. % = 0/25/50/75/100.

| # | WBS | Bước | Môi trường | Priority | Status | % | Evidence | Ghi chú |
|---|-----|------|-----------|----------|--------|---|----------|---------|
| 1 | 0.1 | B0.1 Repo + config + naming | Local | Critical | Not Started | 0 | — | Cấu trúc đề xuất trong PLAN §2, duyệt trước |
| 2 | 0.2 | B0.2 Freeze CONTRACTS.md + sample JSON | Local | Critical | Not Started | 0 | — | Handoff Person 2 (mock artifacts) |
| 3 | 1.1 | B1.1 Ingest CSV explicit schema | Local | Critical | Not Started | 0 | — | Verify row counts vs PRD (ERR2) |
| 4 | 1.2 | B1.2 Clean + transform + join | Local | Critical | Not Started | 0 | — | Quality summary + before/after |
| 5 | 1.3 | B1.3 Curated Parquet + read-back | Local | Critical | Not Started | 0 | — | Append target cho Person 2 streaming |
| 6 | 1.1–1.2 | B1.EDA EDA_REPORT.md | Local | High | Not Started | 0 | — | Yêu cầu riêng: mọi số kèm lệnh sinh |
| 7 | 2.1 | B2.1 Spark SQL + explain('formatted') | Local | High | Not Started | 0 | — | ≥2 phân tích + plan interpretation |
| 8 | 2.2 | B2.2 MapReduce cross-check | Local | Medium | Not Started | 0 | — | Input CSV/Text (risk R3) |
| 9 | 3.1 | B3.1 Split + MODEL_DESIGN §1–2 (seed, rule, leakage) | **Colab** | Critical | Not Started | 0 | — | Chốt temporal vs random trước |
| 10 | 3.2 | B3.2 Movie Mean + Popularity baselines | **Colab** | High | Not Started | 0 | — | Popularity Top-N deterministic |
| 11 | 3.3 | B3.3 Content-Based Similar-Movie Lists | **Colab** | High | Not Started | 0 | — | Chú ý RAM: block-matrix nếu cần |
| 12 | 3.4 | B3.4 ALS + precompute Top-N | **Colab** | Critical | Not Started | 0 | — | rank/reg tunable → justification |
| 13 | 3.5 | B3.5 Evaluation + 4 serving artifacts → metrics.csv | **Colab** | Critical | Not Started | 0 | — | **HANDOFF Person 2 (M2, day 5)** |
| 14 | 6.1 | B6.1 Retrain candidate version | **Colab** | Critical | Not Started | 0 | — | Sau khi Person 2 streaming append (5.2) |
| 15 | 6.2 | B6.2 Promotion gate + rollback logic | Colab/Local | High | Not Started | 0 | — | Fail-path phải giữ nguyên active version |
| 16 | 7.1 | B7.1 Controlled experiment CSV vs Parquet + repro manifest | Local | Medium | Not Started | 0 | — | Warm-up + 3–5 runs, median |
| 17 | 8.1 | B8.1 E2E integration + demo rehearsal | Cả hai | Critical | Not Started | 0 | — | Cùng Person 2 |
| 18 | 8.2 | B8.2 Evidence pack + release tag | Local | Critical | Not Started | 0 | — | Mọi rubric claim có evidence |

## Verify gates (đối chiếu sau mỗi bước — INV3)
- [ ] G0: Person 2 dựng mock artifact từ CONTRACTS.md không hỏi lại
- [ ] G1 (M1, day 2): Parquet read-back schema/counts consistent
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
- 2026-09-25: Khởi tạo checklist (18 mục, tất cả Not Started) theo PLAN_Person1.md.