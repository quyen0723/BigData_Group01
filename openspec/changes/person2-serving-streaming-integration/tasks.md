## 1. Phối hợp Person 1 (gửi ngay, không chặn code — mọi mục có default trong design.md)

- [ ] 1.1 Gửi Quyên danh sách D1–D6 (design.md §Open Questions): popular top-100, kênh bàn giao Drive, ngưỡng gate + cửa sổ train candidate + version candidate FAIL, quy tắc latest-wins, người viết report §10–12/DEPLOYMENT_DESIGN, ký bổ sung contract
- [ ] 1.2 Ghi kết quả chốt D1–D6 vào design.md (hoặc ghi "dùng default") và cập nhật config tương ứng
- [ ] 1.3 Thêm ghi chú additive vào `contracts/CONTRACTS.md` (6 collection mới, 1 doc/(userId, modelVersion) khi staging, field `tier`/`fallbackReason` trong response) sau khi Person 1 ký

## 2. Runtime & môi trường (WBS 0.1 phần Person 2)

- [x] 2.1 Bật Docker Desktop, tải bundle Drive `movielens32m/` về gốc repo (curated/, artifacts/, models/als_v1.0.0/) và kiểm tra checksum/size so với README_COLAB_SETUP — done (đã tải, bootstrap script xác nhận đủ 8 artifact; riêng 2 file `userFactors` bị lỗi 0 byte, xem blocker nhóm 7)
- [x] 2.2 Tạo `docker/docker-compose.yml` với 4 service (mongo cache 3 GB + volume, kafka KRaft, spark, api), healthcheck, mount `movielens32m/` → `/data`
- [x] 2.3 Viết Dockerfile spark (`python:3.12-slim` + OpenJDK 17 + `pyspark==3.5.7`, volume ivy cache cho `spark-sql-kafka` + `mongo-spark-connector`) và Dockerfile api
- [x] 2.4 Tạo `configs/serving.yaml`, `configs/streaming.yaml`, `.env.example`, file dependency phía serving; không hardcode path/credential
- [x] 2.5 Script bootstrap tạo thư mục `stream/{raw_events,quarantine,checkpoints,handoff}` và fail-fast khi thiếu file bundle — verified: chạy thật 4 tình huống (thiếu bundle, thiếu artifact, đủ artifact, chạy lại) đều đúng
- [x] 2.6 Chạy thử stack từ trạng thái sạch; ghi `evidence/p2_env_versions.txt` (image tags, Spark/PySpark, package coordinates, Python packages) — done; đã chạy sạch nhiều lần (kể cả sau khi Docker tự restart qua đêm), ghi cả 5 vấn đề môi trường đã gặp và sửa

## 3. Serving store — MongoDB (WBS 1.4 + 4.1)

- [x] 3.1 Script tạo index idempotent cho 10 collection theo bảng D-4 — verified: chạy 2 lần liên tiếp với Mongo thật (container `movielens-mongo`), cùng kết quả 5 index
- [x] 3.2 Spark job nạp `movies` từ `curated_movies` + tính `support` từ `curated_ratings` (87,585 docs) — verified: chạy thật trong container spark, 87,585 curated rows -> 87,585 docs Mongo, khớp tuyệt đối
- [x] 3.3 Spark job sinh `user_rated` (32,000,204 docs) và `user_history` (200,948 docs, R/P từ config) từ `user_history_seed.parquet` — verified thật: 32,000,204 seed rows -> 32,000,204 user_rated docs (1:1), 200,948 user_history docs, Σinteraction_count = 32,000,204 (khớp tuyệt đối cả 2 chiều)
- [x] 3.4 Loader artifact (Spark, explicit schema, `multiLine`) cho `popular_movies` (1 object), `similar_movies`, `als_topn.json` → `user_recommendations`; kiểm `modelVersion` khớp `--version`; idempotent theo version — verified thật: popular=1 doc, similar=80,505 docs (khớp MODEL_DESIGN.md §4), als_topn=154,608 docs vào `user_recommendations` (khớp MODEL_DESIGN.md §7), đúng tên collection theo CONTRACTS §3.3
- [x] 3.5 Registry + con trỏ: ghi `model_registry{v1.0.0}` và `serving_meta{_id:"active"}` bằng bootstrap gate (chỉ G4–G7) — verified thật: 7/7 check PASS, G5 full-scan 1,546,068 recommendation rows × 32,000,204 rated rows = 0 leaked; v1.0.0 active
- [x] 3.6 Read-back check: count đối chiếu nguồn, `Σ interaction_count = 32,000,204`, min 20 / max 33,332, query mẫu mỗi access pattern → `evidence/p2_4_2_api_traces.txt` — verified qua bootstrap gate (7/7 PASS, đối chiếu mọi collection) + query mẫu qua API thật cho cả 3 tier
- [x] 3.7 `explain()` cho 3 lookup chính (IXSCAN, rated-set covered) → `evidence/p2_4_1_mongo_explain.txt` — verified thật: user_recommendations + similar_movies = IXSCAN+FETCH; user_rated = PROJECTION_COVERED (đúng thiết kế D-4, không cần FETCH)

## 4. Recommendation API + router (WBS 2.3, 2.4, 4.2 → M3)

- [x] 4.1 Tầng repository đọc Mongo (con trỏ active cache TTL, lookup theo version map) — `src/serving/repository.py`: `ServingRepository` Protocol + `MongoServingRepository` (pymongo); code viết xong, CHƯA chạy được với Mongo thật (nằm trong 4.7)
- [x] 4.2 Hàm thuần: chọn tier, chọn seeds, chuỗi hạ cấp ALS→Content→Popularity + `fallbackReason` — `src/serving/router.py` + `tests/unit/test_router.py` (13 test PASS)
- [x] 4.3 Hàm thuần: weighted RRF, tie-break theo `support`/`movieId`, lấp từ popularity, exclusion theo tập `user_rated` — `src/serving/fusion.py` + `src/serving/exclusion.py` + tests (11 test PASS)
- [x] 4.4 FastAPI `GET /recommendations/{userId}?k=` (validate 1 ≤ k ≤ 50, userId > 0) + `/health`; response đúng contract + `tier`/`fallbackReason`; enrich `title`/`genres` — `src/api/main.py`, `src/api/schemas.py`, `src/serving/service.py`; nối dây kiểm bằng TestClient + fake repository (7 test PASS); CHƯA chạy trong container thật
- [x] 4.5 Log JSON-lines mỗi request (userId, tier, strategy, fallbackReason, modelVersion, k, n_returned, latency_ms) — trong `api/main.py::_log_request`, test `test_request_is_logged` PASS
- [x] 4.6 Unit test pytest cho 3 tier + các nhánh hạ cấp + exclusion + determinism (fixture từ `contracts/samples/`) — `tests/unit/test_contract_samples.py` (11 test PASS, đọc trực tiếp `contracts/samples/*.json`)
- [x] 4.7 Integration test trên stack thật: user tier 0 (userId mới), user warm có ALS, user cold-start 46k (không ALS) — chứng minh 0 phim đã rate; lưu trace → `evidence/p2_4_2_api_traces.txt` (M3) — verified thật với data 200,948 user: userId=1 (ALS+CONTENT), userId=127249 (CONTENT+POPULARITY, fallbackReason=als_artifact_missing), userId=999999999 (POPULARITY, khớp tuyệt đối popular_movies.json), exclusion 141 phim đã rate = 0 overlap, input validation 422 đúng cả 3 case

## 5. Thí nghiệm chọn ngưỡng T (D-11)

- [x] 5.1 Ghi quy tắc quyết định vào `docs/MODEL_DESIGN.md` (mục "Ngưỡng T") **trước** khi chạy — done (`docs/MODEL_DESIGN.md` §9b)
- [ ] 5.2 Spark job: tập user chung (có history < cut_test, có relevant ≥ 4.0 sau cut_test, có ALS factor); ALS từ `ALSModel.load` loại item rated < cut_test; Content từ positives < cut_test; Popularity tính lại trên < cut_test — **BLOCKED: cần `ALSModel.load()`, cùng gốc lỗi model Drive với nhóm 7 #11**
- [ ] 5.3 Tính HitRate@10 / NDCG@10 theo bucket + n + CI 95% bootstrap → `evidence/p2_tier_threshold.csv` — BLOCKED (phụ thuộc 5.2)
- [ ] 5.4 Áp quy tắc, cập nhật T trong `configs/serving.yaml` (bỏ nhãn provisional), ghi kết quả + diễn giải vào MODEL_DESIGN.md — BLOCKED (phụ thuộc 5.2/5.3)

## 6. Kafka + Structured Streaming (WBS 5.1, 5.2 → M4)

- [x] 6.1 Tạo topic `ratings.v1` (3 partitions); producer simulator (confluent-kafka, acks=all, idempotence, key=userId) với các mode: scenario, random, invalid, duplicate → `evidence/p2_5_1_kafka_produce_consume.txt` — verified thật qua `kafka:9092` (đường nội bộ); phát hiện: cổng host 9094 chập chờn do Docker Desktop/WSL2 trên Windows, đã ghi chú vào streaming.yaml
- [x] 6.2 Q1 raw: Kafka → parquet file sink `stream/raw_events` (partition ingest_date) + checkpoint riêng — verified: file thật landed, đọc lại được
- [x] 6.3 Parse + validate (luật D-9, broadcast join `curated_movies`, session timezone UTC); Q3 quarantine file sink kèm `reason` — verified thật: gửi 6 event lỗi cố ý, cả 6 đúng lý do riêng (invalid_event_id/invalid_user_id/unknown_movie_id/invalid_rating_value/invalid_timestamp×2) + bắt được 1 message rác từ debug trước đó
- [x] 6.4 Q2 valid: watermark 10 phút + `dropDuplicatesWithinWatermark(eventId)` → `foreachBatch(serve_batch)` + checkpoint riêng — verified: 3 query chạy đồng thời không lỗi
- [x] 6.5 `serve_batch` theo thứ tự D-10: skip batchId đã commit → lọc ledger → append `curated_ratings` (batch writer, partitionBy year, cột §2.1) → upsert `user_rated` latest-wins → tính lại `user_history` → insert ledger → commit batchId — verified thật: userId=300001 tier 0→few đúng ngay sau khi rate, idempotency xác nhận (gửi 3 lần 1 eventId → ledger chỉ 1 dòng, interaction_count không đổi)
- [x] 6.6 Unit test hàm cập nhật `user_history` (move-to-front, cap R/P, re-rate không tăng count, replay cho cùng kết quả) — `src/serving/history.py` + `tests/unit/test_history.py` (9 test PASS); hàm này được `serve_batch` gọi lại trong Spark job thật (`src/streaming/pipeline.py`)
- [x] 6.7 Kiểm chứng: GET trước/sau khi rate thấy history mới; curated read-back = 32,000,204 + N và không có `_spark_metadata` trong `curated_ratings`; log `lastProgress` → `evidence/p2_5_2_streaming.txt` (M4) — verified thật cả 2 điều kiện: API đổi tier ngay, `_spark_metadata` không tồn tại trong curated_ratings

## 7. Retraining orchestration + promotion gate (WBS 6.1, 6.2 → M5, cùng Person 1)

- [x] 7.1 `retrain_trigger`: đếm event đã áp dụng sau watermark, ngưỡng `N_min`/`--force`/`--interval`; xuất `delta_ratings.parquet` + `manifest.json` (checksum), tiến watermark — verified thật: dưới ngưỡng đúng từ chối, `--force` xuất đúng handoff (7 dòng, 1 user, newUserCount=1), rerun sau đó thấy watermark đã tiến (0 pending)
- [ ] 7.2 Bàn giao package cho Person 1 qua kênh D2; nhận `candidates/<version>/` (artifact + model_card + model) — **BLOCKED: cần Quyên trả lời D2 (kênh Drive) + gửi candidate thật**
- [x] 7.3 Import candidate staged (loader `--stage`), registry `status=staged`; kiểm API vẫn trả version cũ — verified thật với candidate tổng hợp v1.1.0 (154,608+80,505+1 docs), API vẫn trả v1.0.0 sau khi stage
- [x] 7.4 `promotion_gate`: `ALSModel.load` active + candidate, RMSE cùng holdout; G1–G7; report JSON vào registry + evidence — code hoàn chỉnh, chạy thật; G4/G5/G6/G7 PASS trên dữ liệu thật; G1-G3 (RMSE) FAIL vì **phát hiện lỗi thật: 2/10 file parquet `userFactors` của model `als_v1.0.0` gốc bị 0 byte (tải Drive thiếu)** — xem chi tiết trong Blocker bên dưới
- [x] 7.5 Activate (1 `updateOne` con trỏ, registry active/retired) và nhánh FAIL (con trỏ không bị ghi, registry rejected) — nhánh FAIL verified thật: `serving_meta.activatedAt` không đổi so với lần bootstrap gốc, API vẫn trả v1.0.0, `model_registry.v1.1.0.status="rejected"`. Nhánh PASS: code viết xong (`promotion_gate.py`), CHƯA verify được vì cần model không lỗi
- [x] 7.6 Lệnh `--rollback` (kiểm docs previous còn tồn tại) và `cleanup --keep 2` — code viết xong (`orchestration/manage_versions.py`), CHƯA verify được vì chưa có lần activate PASS nào để rollback từ đó
- [ ] 7.7 Chạy fail-path với candidate cố ý kém của Person 1 (con trỏ trước/sau giống hệt) và pass-path với candidate chuẩn (response đổi `modelVersion`) → `evidence/p2_6_2_promotion_{fail,pass}.txt` (M5) — fail-path verified thật (xem 7.5, evidence đã lưu); pass-path **BLOCKED: cần model active không lỗi (tải lại Drive) + candidate thật khác biệt từ Quyên**

**⚠️ BLOCKER phát hiện khi test thật (2026-09-26):** `movielens32m/models/als_v1.0.0/userFactors/part-00000` và `part-00001` (2 trong 10 file) là **0 byte** — tải từ Drive bị thiếu, không phải lỗi code (đã xác nhận `itemFactors/` và `metadata/` đều nguyên vẹn). Cần tải lại `models/als_v1.0.0/` từ Drive (toàn bộ hoặc riêng `userFactors/`) trước khi có thể verify G1-G3 (RMSE) và pass-path của promotion gate. Nên báo Quyên kiểm tra bản Drive gốc có bị lỗi tương tự không.

## 8. Validation, failure paths & observability (WBS 7.2 → M6)

- [x] 8.1 Script test matrix: event không hợp lệ (quarantine, state không đổi), user không tồn tại, exclusion artifact cũ, replay eventId, kill/restart stream, thiếu doc ALS, k ngoài biên, gate FAIL/PASS, rollback → `evidence/p2_7_2_test_matrix.csv` — 24 case, 21 PASS thật + 3 BLOCKED (đã ghi rõ lý do: model ALS lỗi trên Drive). Điểm mới verify thật lần này: **fresh-history exclusion** (rate lại đúng phim ALS gợi ý qua Kafka → bị loại ngay dù doc precompute chưa đổi) và **kill/restart streaming** (Docker tự restart qua đêm ngoài ý muốn — pipeline lên lại từ checkpoint không lỗi, không xử lý trùng, batchId tiếp tục tăng)
- [x] 8.2 Load test ≥ 1,000 request qua các tier + script tổng hợp (strategy distribution, fallback rate, p50/p95) → `evidence/p2_7_2_api_latency.txt` — verified thật: N=1000, p50=25.8ms, p95=98.8ms, p99=163.6ms, 0 lỗi 5xx, mọi request đều có log JSON-lines
- [x] 8.3 Rà changed files: không còn TODO/stub/test skip; mọi test pass — verified: `grep` không thấy TODO/FIXME/skip nào trong `src/`, `tests/`; 67/67 test PASS

## 9. Tích hợp E2E, tài liệu & evidence pack (WBS 8.1, 8.2 → M7, M8)

- [x] 9.1 Script demo E2E: user mới tier 0 → rate qua Kafka → Few; user warm (userId=1) → ALS + fresh-history exclusion → replay eventId idempotent → `scripts/demo_e2e.py` — verified thật 2 lần (userId 300099, 300100), 5/5 assertion PASS mỗi lần. Nhánh gate FAIL/PASS với candidate thật CHƯA gộp vào script (BLOCKED bởi model Drive lỗi, xem nhóm 7 #11)
- [x] 9.2 Cập nhật README: run sequence phần Person 2 từ `docker compose up` tới demo, kèm tên evidence mỗi bước — done, đối chiếu đúng lệnh thật đã chạy trong session
- [x] 9.3 Viết `docs/DEPLOYMENT_DESIGN.md` (driver/executor, storage, scaling, fault tolerance, observability, security, 1 trade-off cost/perf, CAP/consistency) — done, có trích dẫn evidence thật (RAM 8GB không đủ, build_user_state ~11 phút)
- [x] 9.4 Sơ đồ kiến trúc đánh dấu Implemented / Design-only cho từng block (Policy Filter, cluster deploy, Airflow = design-only) — done, cập nhật `docs/SERVING_ARCHITECTURE.md` chú thích màu + trạng thái
- [ ] 9.5 Soạn nội dung report §10 (NoSQL), §11 (Streaming), §12 (Deployment) + đóng góp Person 2 cho Appendix C — chưa viết (nội dung prose cho báo cáo cuối, không phải artifact repo)
- [x] 9.6a Tạo `CHECKLIST_Person2.md` theo từng mục — done
- [ ] 9.6b Tổng rehearsal demo cùng Person 1; tag release cùng Person 1 (M8) — cần lịch chung với Quyên, chưa làm
