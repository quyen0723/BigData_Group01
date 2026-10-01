# CHECKLIST — Person 2 (Hiển) — Serving, Streaming & Integration

> Quy tắc (tracker rule 1): DONE ⟺ code runs + output correct + evidence exists + downstream consume được.
> Nguồn chi tiết: `openspec/changes/person2-serving-streaming-integration/{proposal,design,specs,tasks}.md`.
> Trạng thái ∈ {Not Started, In Progress, Blocked, Done}. % = 0/25/50/75/100.

| # | WBS | Bước | Môi trường | Priority | Status | % | Evidence | Ghi chú |
|---|-----|------|-----------|----------|--------|---|----------|---------|
| 1 | 1.4 | Mongo serving schema (index + collection) | Docker | High | **Done** | 100 | `evidence/p2_4_1_mongo_readback.txt` (nêu trong tasks.md #3.6), `p2_4_1_mongo_explain.txt` | 10 collection (4 contract + 6 additive); index tạo idempotent, verify 2 lần liên tiếp |
| 2 | — | Nạp M2 vào Mongo (movies, user_rated, user_history, 3 artifact) | Docker | Critical | **Done** | 100 | `tasks.md` #3.2–3.5 | 87,585 movies · 32,000,204 user_rated · 200,948 user_history · 154,608 user_recommendations · 80,505 similar_movies · 1 popular_movies — mọi số khớp M2 handoff |
| 3 | — | Bootstrap gate + activate v1.0.0 | Docker | Critical | **Done** | 100 | bootstrap gate log (tasks.md #3.5) | 7/7 check PASS, G5 full-scan 1,546,068 recs × 32,000,204 rated = 0 leaked |
| 4 | 2.3 | Recommendation API skeleton | Docker | High | **Done** | 100 | `tests/unit/test_api.py` (7 test) | FastAPI, `/health`, dependency injection cho test |
| 5 | 2.4 | History-tier router 0/Few/Enough | — | Critical | **Done** | 100 | `tests/unit/test_router.py` (13 test) | + chuỗi hạ cấp ALS→Content→Popularity, `fallbackReason` |
| 6 | 4.1/4.2 | Online candidate retrieval, exclusion, fusion, Top-N | Docker | Critical | **Done** | 100 | `evidence/p2_4_2_api_traces.txt` | 3 tier thật (ALS+CONTENT / CONTENT+POPULARITY / POPULARITY) đúng contract; fresh-history exclusion verified |
| 7 | 5.1 | Kafka rating-event flow | Docker | High | **Done** | 100 | `evidence/p2_5_1_kafka_produce_consume.txt` | Topic `ratings.v1`, đường nội bộ `kafka:9092` ổn định; cổng host 9094 chập chờn (ghi chú, không dùng cho pipeline thật) |
| 8 | 5.2 | Structured Streaming validate + state update | Docker | Critical | **Done** | 100 | `evidence/p2_5_2_streaming.txt` | 3 query (raw/valid/quarantine); idempotent (replay 3× 1 eventId → hiệu ứng 1 lần); resume đúng sau khi Docker bị restart ngoài ý muốn |
| 9 | 6.1 | Retrain trigger + handoff package | Docker | Critical | **Done** | 100 | session log 2026-09-26 (tasks.md #7.1) | Ngưỡng N_min + `--force`; manifest.json + delta_ratings.parquet + checksum |
| 10 | 6.1 | Stage candidate | Docker | Critical | **Done** | 100 | session log 2026-09-26 (tasks.md #7.3) | Candidate tổng hợp v1.1.0 (154,608+80,505+1 docs) staged, API vẫn trả v1.0.0 |
| 11 | 6.2 | Promotion gate (G1–G7) + fail-path | Docker | Critical | **Blocked (một phần)** | 75 | `evidence/p2_6_2_promotion_fail_run_log.txt` + `.json` | G4–G7 PASS thật; G1–G3 (RMSE) **BLOCKED**: 2 file `userFactors` của model `als_v1.0.0` trên Drive bị 0 byte (đã báo Quyên, đã tải lại 2 lần vẫn lỗi — lỗi ở nguồn Drive). Fail-path verified: `serving_meta` không đổi 1ms |
| 12 | 6.2 | Rollback / cleanup | Docker | High | **Blocked** | 50 | `src/orchestration/manage_versions.py` | Code xong, chưa test được vì chưa có lần `activate` PASS nào để rollback từ đó (phụ thuộc #11) |
| 13 | 7.2 | Test matrix + load test | Docker | Medium | **Done** | 100 | `evidence/p2_7_2_test_matrix.csv` (24 case), `p2_7_2_api_latency.txt` | 21/24 PASS thật, 3 BLOCKED (đều do #11); load test N=1000, p50=25.8ms p95=98.8ms, 0 lỗi 5xx |
| 14 | 8.1 | E2E integration + demo rehearsal | Docker | Critical | In Progress | 60 | — | Từng bước đã verify riêng lẻ (tier 0→Few→Enough, gate fail); script gộp thành 1 kịch bản demo liền mạch — chưa viết |
| 15 | 8.2 | Evidence pack + docs (README, DEPLOYMENT_DESIGN, diagram) | Local | Critical | **Done** | 100 | `docs/DEPLOYMENT_DESIGN.md`, `docs/SERVING_ARCHITECTURE.md`, README §Person 2 | Driver/executor, storage, scaling, fault tolerance, observability, security, 1 trade-off, CAP đều có |

## Verify gates (đối chiếu sau mỗi bước)
- [x] M3 (Serving Integration Ready): 0/Few/Enough trả đúng nguồn, không phim đã rate — PASS 2026-09-26 (`evidence/p2_4_2_api_traces.txt`)
- [x] M4 (Streaming Feedback Ready): rating mới xuất hiện trong history + curated ngay — PASS 2026-09-26/27 (`evidence/p2_5_2_streaming.txt`, resume sau restart)
- [ ] M5 (Model Refresh Ready): fail giữ nguyên active — **PASS một phần** (fail-path xong); pass path + rollback **chờ** model Drive sửa + candidate thật từ Quyên
- [x] M6 (Performance & Validation Ready): test matrix + load test — PASS 2026-09-27
- [ ] M7 (Final E2E Demo): batch → serving → feedback → refresh liền mạch — chưa gộp thành 1 script/kịch bản
- [ ] M8 (Final Freeze): evidence pack đầy đủ cho MỌI claim rubric — DEPLOYMENT_DESIGN + README xong; report §10–12 nội dung + Appendix C đóng góp Person 2 chưa viết

## Blockers / Decisions pending
| Ngày | Vấn đề | Owner | Next action |
|------|--------|-------|-------------|
| 2026-09-26 | 2 file `userFactors/part-00000`, `part-00001` của `models/als_v1.0.0` là 0 byte trên Drive | Quyên | Đã báo (nội dung tin nhắn kỹ thuật đã gửi 2026-09-27). Chờ Quyên re-save model từ Colab + upload lại |
| — | D1–D4 (design.md §Open Questions): popular top-100, kênh bàn giao Drive, ngưỡng gate ε/band, cửa sổ train candidate | Quyên | Chưa hỏi chính thức — đang dùng default ghi trong design.md |
| — | Ai viết report §10–12 + Appendix C | Cả hai | Đề xuất Person 2 (Hiển) do trực tiếp làm phần này |

## Lịch sử cập nhật
- 2026-09-27: Nhóm 8 (test matrix 24 case, load test N=1000) + nhóm 9 một phần (`DEPLOYMENT_DESIGN.md`, README §Person 2, sơ đồ kiến trúc cập nhật Implemented). Phát hiện: fresh-history exclusion verified; Docker tự restart qua đêm → streaming resume đúng (test kill/restart thật, không định trước). Model Drive tải lại vẫn 0 byte — xác nhận lỗi nguồn, đã soạn tin báo Quyên.
- 2026-09-26 (đêm): Nhóm 7 (retrain_trigger, stage_candidate, promotion_gate, manage_versions) — verified thật fail-path; phát hiện 3 bug môi trường (connector Mongo sai bản, thiếu numpy, thiếu distutils/setuptools shim cho Python 3.12) đều đã sửa và verify lại. Phát hiện model corrupt (0 byte) khi chạy G1-G3.
- 2026-09-26: Nhóm 3 (Mongo loader) + nhóm 4 (API) + nhóm 6 (Kafka streaming) — verified thật 100% với dữ liệu M2 đầy đủ (32,000,204 rating, 200,948 user). Đạt M3 + M4. 4 bug môi trường phát hiện và sửa: connector version, WSL restart giữa build, cổng Kafka host chập chờn, cổng 8000 bị Laragon chiếm.
- 2026-09-26: Nhóm 2 (Docker Compose runtime) + toàn bộ hàm thuần nhóm 4 (router/fusion/exclusion/history) + streaming validation rules — 67 unit test PASS. Khởi tạo `openspec/changes/person2-serving-streaming-integration/`.
