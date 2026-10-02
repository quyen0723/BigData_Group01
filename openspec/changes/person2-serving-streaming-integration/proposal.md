## Why

Person 1 đã bàn giao M2 (serving artifacts + ALS `v1.0.0`, mọi gate PASS) nhưng toàn bộ phần online của kiến trúc — streaming path (Layer 1), Online Serving (Layer 2B) và Feedback/Model Refresh (Layer 3) — **chưa có dòng code nào** trong repo. Đề bài BDA501 bắt buộc: NoSQL write + read-back có biện minh data model/access pattern, một Structured Streaming path tối thiểu (source, sink, checkpoint, event-time/state), cloud/cluster deployment design và demo end-to-end. Tracker của Person 2 đang trễ ~1 ngày (WBS 1.4/2.3/2.4 hạn 25–26/09), còn M3 → M8 dồn trong 26/09–03/10.

Đọc source trong lúc explore phát hiện 4 điểm sẽ chặn nếu làm theo hướng dẫn hiện có:
- `popular_movies.json` là **1 object** (không phải array) và chỉ có **10 items** → `mongoimport --jsonArray` sai với file này, và không đủ để trả `k=10` sau exclusion/bổ sung.
- `mongoimport --jsonArray` bị MongoDB giới hạn **16 MB**, trong khi `als_topn.json` = 94 MB, `similar_movies.json` = 82 MB.
- Streaming file sink ghi vào `curated_ratings/` sẽ tạo `_spark_metadata/`, khiến mọi batch read sau đó (retrain) **chỉ thấy file của stream** → 32M dòng lịch sử bị ẩn (đã kiểm chứng trong `DataSource.resolveRelation`, Spark 3.5).
- Máy chạy là Windows 11 (Spark ghi Parquet/checkpoint cần winutils), system Python chưa có pyspark/pymongo, Docker Desktop đã cài nhưng chưa chạy.

## What Changes

- **Runtime tái lập được**: Docker Compose gồm MongoDB (single-node), Kafka (KRaft, single broker), Spark 3.5.x (PySpark khớp `pyspark==3.5.7` của Person 1) và Recommendation API; config qua YAML + biến môi trường, không có credential trong source.
- **Serving store (MongoDB)**:
  - Nạp 3 artifact theo contract (`popular_movies`, `similar_movies`, `user_recommendations`) bằng Spark/pymongo batch, không dùng `mongoimport --jsonArray`.
  - Sinh `user_history` bằng aggregate từ `user_history_seed.parquet` (§3.4, bounded arrays).
  - Thêm các collection **additive** (ngoài contract, không phá schema cũ): `movies` (title/genres + support để enrich/re-rank), `user_rated` (tập phim đã rate chính xác, phục vụ exclusion), `rating_events` (ledger idempotency theo `eventId`), `serving_meta` (con trỏ active version), `model_registry` (trạng thái từng version), `pipeline_state` (watermark của stream/handoff).
  - Version hoá theo `modelVersion` + compound index; activate/rollback = cập nhật **1 document** con trỏ (atomic).
- **Recommendation API** `GET /recommendations/{userId}?k=10`:
  - Router 0 / Few / Enough theo `interaction_count` với ngưỡng T tunable.
  - Chuỗi hạ cấp ALS → Content → Popularity, kèm `fallbackReason` (bao gồm 46,340 user cold-start không có doc ALS).
  - Exclude already-rated chính xác qua `user_rated`, fusion rank-based (weighted RRF), enrich `title`/`genres`, bounded `k`.
  - Response luôn có `modelVersion`; thêm các field additive `tier` và `fallbackReason`.
- **Rating event pipeline**:
  - Producer simulator gửi vào Kafka topic `ratings.v1` (key = `userId`), đọc bằng Structured Streaming.
  - Raw Event Storage (bronze) → validate + quarantine → dedup `eventId` (watermark + ledger).
  - `foreachBatch` append vào Curated Parquet (batch write, **không** file sink) và cập nhật idempotent `user_history`/`user_rated`; có checkpointing.
- **Retraining orchestration** (Person 2 điều phối; Person 1 train):
  - Trigger theo lượng event mới hoặc lịch, rồi xuất delta + manifest để bàn giao.
  - Import candidate ở trạng thái *staged* (chưa phục vụ).
  - Promotion gate kiểm tra lại độc lập bằng `ALSModel.load()` trên cùng holdout, cộng thêm kiểm tra toàn vẹn artifact.
  - PASS thì activate; FAIL thì `v1.0.0` tiếp tục phục vụ; có lệnh rollback.
- **Thí nghiệm chọn T**: chia user theo số tương tác train, so HitRate@10/NDCG@10 của ALS, Content và Popularity **trên cùng tập user**; ghi kết quả vào `MODEL_DESIGN.md`.
- **Validation & bàn giao**:
  - Test matrix WBS 7.2, kịch bản demo E2E (user mới chuyển tier 0 → Few → Enough, gate FAIL rồi PASS, replay `eventId`).
  - Evidence `evidence/p2_*`, `CHECKLIST_Person2.md`.
  - `docs/DEPLOYMENT_DESIGN.md` (hạng mục rubric chưa ai nhận) và đánh dấu Implemented/Proposed trên sơ đồ kiến trúc.
- **Contract**: không có thay đổi BREAKING. Có một điểm cần Person 1 ký xác nhận (CONTRACTS §0 FROZEN): trong lúc staging, `user_recommendations` chứa **1 doc cho mỗi (userId, modelVersion)** thay vì 1 doc cho mỗi userId. Schema doc giữ nguyên.
- **Phụ thuộc Person 1** (open decisions, chi tiết trong design.md):
  - D1: xuất lại `popular_movies` top-100.
  - D2: kênh bàn giao delta/candidate qua Drive.
  - D3: ngưỡng gate và cửa sổ dữ liệu retrain.
  - D4: quy tắc latest-wins khi user rate lại cùng một phim.

## Capabilities

### New Capabilities
- `serving-runtime`: môi trường Docker Compose tái lập được (Mongo, Kafka, Spark, API), quản lý config/secret, lệnh chạy chuẩn từ trạng thái sạch.
- `serving-store`: data model MongoDB (4 collection theo contract + 6 collection additive), index theo access pattern, nạp artifact và sinh `user_history`, version hoá + con trỏ active, bằng chứng read-back.
- `recommendation-api`: endpoint gợi ý, validate input, router theo tier với ngưỡng T tunable (chọn bằng thí nghiệm), chuỗi hạ cấp, exclusion, fusion/re-rank, enrich, response contract và log quan sát.
- `rating-stream-ingestion`: event contract trên Kafka, producer simulator, Structured Streaming (raw storage, validate/quarantine, dedup, checkpoint), append Curated Parquet và cập nhật idempotent serving state.
- `model-refresh-orchestration`: trigger retrain, bàn giao delta/manifest, import candidate staged, promotion gate, activate/rollback atomic, audit trong `model_registry`.

### Modified Capabilities
<!-- Chưa có spec nào trong openspec/specs/ — không có capability bị sửa. -->

## Impact

- **Code mới**: `docker/` (compose + Dockerfile), `src/serving/`, `src/api/`, `src/streaming/`, `src/orchestration/`, `src/experiments/`, `tests/`. Không sửa code của Person 1 trong `src/etl`, `src/analytics`, `src/modeling`.
- **Config mới**: `configs/serving.yaml`, `configs/streaming.yaml`, `.env.example`. `configs/requirements.txt` tách thêm file dependency cho phía serving.
- **Dependencies**:
  - Python: `pymongo`, `fastapi`, `uvicorn`, `pyarrow`, `pytest`, `httpx`.
  - Spark packages: `spark-sql-kafka-0-10_2.12` (khớp Spark 3.5.x), `mongo-spark-connector_2.12` 10.x.
  - Images: `mongo`, `apache/kafka`.
- **Dữ liệu local**:
  - Bundle Drive `movielens32m/` (~1 GB, đã gitignore) được mount vào container.
  - Volume Mongo ~3–4 GB (`user_rated` ≈ 32M docs).
  - Thư mục stream (raw/quarantine/checkpoints) nằm dưới `movielens32m/stream/`.
- **Tài liệu**:
  - Thêm mục T vào `docs/MODEL_DESIGN.md` (phối hợp Person 1).
  - Ghi chú additive vào `contracts/CONTRACTS.md` (cần P1 ký).
  - Thêm run sequence cho phần serving/streaming vào README.
  - Thêm `docs/DEPLOYMENT_DESIGN.md` và sơ đồ có đánh dấu Implemented/Proposed.
- **Rủi ro lịch**: ~7 ngày cho toàn bộ phạm vi. Thứ tự ưu tiên: Serving (M3) → Streaming (M4) → Refresh (M5) → Validation/E2E (M6–M8), tránh rủi ro R4 (làm streaming quá sớm).
