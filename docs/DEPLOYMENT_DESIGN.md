# DEPLOYMENT_DESIGN.md — Cloud/Cluster Deployment (Person 2, WBS 9.3)

> Đáp ứng đề bài BDA501 §2 "Cloud/cluster deployment": kiến trúc triển khai Spark trên
> Standalone/YARN/Kubernetes hoặc dịch vụ Spark quản lý, vị trí driver/executor, storage,
> scaling, fault tolerance, observability, security, và 1 trade-off chi phí/hiệu năng.
> Trạng thái mỗi mục ghi rõ **Implemented** (đã chạy thật trong repo này) hay
> **Proposed / Design-only** (thiết kế cho production, chưa triển khai trong phạm vi course).

## 1. Những gì đã Implemented (dev/demo, Docker Compose)

Toàn bộ phần Person 2 hiện chạy bằng Docker Compose trên 1 máy — đúng phạm vi course
(PRD §Scope: "cluster/cloud production deployment" là mức "Proposed"). Xem
[docker/docker-compose.yml](../docker/docker-compose.yml).

| Service | Đã chạy | Vai trò |
|---|---|---|
| `mongo` (mongo:7.0) | ✅ | Serving store, single node |
| `kafka` (apache/kafka:4.3.1, KRaft) | ✅ | Rating event transport, 1 broker, 3 partition |
| `spark` (Spark 3.5.7, `local[*]`) | ✅ | Loader jobs và orchestration chạy bằng `docker compose exec` |
| `streaming` (cùng image với `spark`) | ✅ | Structured Streaming pipeline (`python -m streaming.pipeline`) chạy như service riêng: `restart: unless-stopped`, healthcheck, giới hạn log. Tự chạy lại sau khi Docker Desktop khởi động lại hoặc JVM sập và resume từ checkpoint (đã kiểm chứng, `evidence/p2_streaming_latency.txt`). Ở production tương ứng với K8s Deployment `replicas: 1` (§2.1) |
| `api` (FastAPI + pymongo) | ✅ | Recommendation API |
| `mongo-express` (1.0.2) | ✅ | **Dev-only**: giao diện web xem/CRUD MongoDB, chỉ bind `127.0.0.1:8081`, có basic auth (`.env`). Không triển khai ở production — ở production dùng Compass/Atlas UI với user MongoDB riêng theo least-privilege (§2.6) |

**Đã đo thật** (evidence/p2_*): 200,948 user_history, 32,000,204 user_rated, 154,608
user_recommendations nạp thành công; API phục vụ p50=25.8ms/p95=98.8ms qua 1,000 request;
streaming pipeline resume đúng sau khi bị Docker restart ngoài ý muốn.

**Giới hạn đã biết của môi trường dev này** (không phải giả định — đo được):
- Spark chạy `local[*]`: driver và "executor" là cùng 1 JVM. Không có phân tán thật.
- Mongo/Kafka single-node: không có replica, không chịu được node failure.
- Máy dev cần ≥16 GB RAM cấp cho Docker (WSL2) mới đủ chạy Spark job trên 32M dòng ổn
  định — đã tự đo: 8GB không đủ, dễ OOM khi nạp `user_rated` (32M docs).

## 2. Kiến trúc production đề xuất (Proposed / Design-only)

### 2.1 Spark: Kubernetes (native) hoặc dịch vụ quản lý

**Đề xuất chính: Spark on Kubernetes** (native `spark-submit --master k8s://...`), vì:
- Cùng công nghệ container hoá đã dùng ở dev (Docker) — đường nâng cấp tự nhiên, không phải học lại Yarn.
- Autoscaling theo pod, cô lập tài nguyên giữa loader/streaming/orchestration job.
- Thay thế được bằng dịch vụ quản lý (AWS EMR, Databricks, GCP Dataproc) nếu muốn giảm vận hành K8s — đánh đổi ở mục 2.7.

| Job | Driver | Executor | Lịch chạy |
|---|---|---|---|
| Loader (3.2–3.5) | 1 pod, resource vừa (2 vCPU/4GB) | 4–8 pod, scale theo dữ liệu | Batch, khi có M2 handoff mới |
| Structured Streaming (pipeline.py) | 1 pod **long-running** | 2–4 pod cố định | Chạy liên tục (Deployment, không phải Job) |
| Retrain trigger + gate | 1 pod | theo nhu cầu | Cron (K8s CronJob) hoặc Airflow |

**Driver placement**: Streaming driver phải là singleton (Structured Streaming không hỗ trợ multi-driver cho cùng query) — dùng K8s Deployment với `replicas: 1` + `livenessProbe` để tự khởi động lại khi crash, kết hợp checkpoint trên storage bền (mục 2.2) để không mất tiến độ khi pod bị thay.

### 2.2 Storage: tách theo đặc tính truy cập

| Dữ liệu | Production | Lý do |
|---|---|---|
| Curated Parquet, raw_events, quarantine | Object storage (S3/GCS) qua `s3a://`/`gs://` | Bền vững, tách rời vòng đời compute, đọc song song tốt cho Spark |
| Checkpoint streaming | Object storage cùng bucket, prefix riêng | Bắt buộc: Structured Streaming cần checkpoint sống sót qua restart pod (mục 2.3) |
| MongoDB data | Managed (Atlas) hoặc EBS/PD có snapshot | Cần backup point-in-time, không phù hợp lưu trên pod ephemeral |
| ALS model artifact | Object storage, versioned theo `als_<version>/` | Khớp quy ước hiện tại (`models/als_<version>`), dễ rollback bằng cách trỏ lại version cũ |

Ở dev, `movielens32m/` đóng vai trò placeholder cho object storage này (mount bind).

### 2.3 Scaling

- **Spark loader/streaming**: scale theo executor (`spark.dynamicAllocation.enabled` trên K8s, hoặc scale thủ công theo kích thước `curated_ratings`/lưu lượng Kafka).
- **API**: stateless (đọc Mongo mỗi request, không giữ session) → scale ngang tự do bằng K8s HPA theo CPU hoặc theo latency p95. Đây là lý do thiết kế API không cache model trong process, chỉ cache con trỏ `serving_meta` với TTL ngắn (`configs/serving.yaml: serving_meta_cache_ttl_seconds`).
- **Kafka**: tăng partition của `ratings.v1` khi throughput vượt khả năng 1 consumer group; hiện dùng 3 partition (đủ cho demo, xem `configs/streaming.yaml`).
- **MongoDB**: shard theo `userId` băm (hashed shard key) cho `user_history`, `user_rated`, `user_recommendations` khi vượt quy mô 1 replica set — các collection này đều truy vấn theo `userId` nên hash-sharding phân tải đều mà không cần truy vấn scatter-gather.

### 2.4 Fault tolerance

| Thành phần | Cơ chế | Trạng thái |
|---|---|---|
| Structured Streaming | Checkpoint trên storage bền + Kafka offset commit qua checkpoint (không qua consumer group Kafka) | **Implemented** ở dev (đã test: kill/restart pipeline resume đúng, xem `evidence/p2_5_2_streaming.txt`) |
| `serve_batch` idempotency | Recompute (không `$inc`) + ledger `rating_events` theo `eventId` | **Implemented**, verified (replay 3 lần 1 eventId → hiệu ứng 1 lần) |
| Mongo | Replica set (3 node) production; single node ở dev | Proposed cho production |
| Kafka | Replication factor 3, `min.insync.replicas=2` production; RF=1 ở dev | Proposed cho production |
| API | Stateless, không có state cần khôi phục; K8s tự restart pod chết | Proposed (K8s liveness/readiness probe) |
| Promotion gate | Fail-closed: bất kỳ lỗi nào (kể cả model không đọc được) đều bị coi là FAIL, `serving_meta` không bị đổi | **Implemented**, verified thật (model lỗi → gate FAIL an toàn, xem `evidence/p2_6_2_promotion_fail_run_log.txt`) |

### 2.5 Observability

- **Đã implement**: API ghi log JSON-lines mỗi request (`tier`, `strategy`, `fallbackReason`, `modelVersion`, `latency_ms`) — xem `src/api/main.py::_log_request`; Spark Structured Streaming tự log `lastProgress` (input/processed rows per sec, batch duration).
- **Proposed cho production**:
  - Export log JSON-lines qua Fluentd/Vector → OpenSearch hoặc CloudWatch Logs, dashboard theo `strategy distribution`, `fallback rate` (đã có công thức tính trong `evidence/p2_7_2_api_latency.txt`, chỉ cần thay nguồn log).
  - Spark: bật `spark.eventLog.enabled` + History Server, hoặc Spark UI proxy qua K8s Ingress cho từng job.
  - Metric: Prometheus exporter cho MongoDB (`mongodb_exporter`) + Kafka (`kafka_exporter`) → Grafana.
  - Alert: fallback rate tăng đột biến (dấu hiệu artifact thiếu), streaming lag tăng (dấu hiệu consumer chậm), promotion gate FAIL liên tiếp.

### 2.6 Security

- **Đã áp dụng ở dev** (đúng NFR trong PRD §18): không hardcode credential trong source — `MONGO_URI`, `KAFKA_BOOTSTRAP_SERVERS` đọc từ biến môi trường (`.env`, gitignored); `.env.example` chỉ chứa placeholder.
- **Proposed cho production**:
  - Secret quản lý bằng Kubernetes Secrets hoặc secret manager (AWS Secrets Manager/GCP Secret Manager), không đặt trong biến môi trường plain-text của pod spec.
  - MongoDB: bật auth (SCRAM), TLS cho kết nối `connection.uri`; user riêng cho loader (write) và API (read-only) theo nguyên tắc least-privilege.
  - Kafka: SASL/TLS thay cho PLAINTEXT hiện tại (chỉ chấp nhận PLAINTEXT ở dev nội bộ).
  - API: rate limiting theo IP/API key, input đã validate (`k` bound, `userId` dương, và từ `add-demo-web-client`: `POST /ratings` validate `rating`/`movieId`/`eventId` trước khi publish Kafka — đã implement), không log giá trị nhạy cảm.
  - Network: Spark/Mongo/Kafka không expose ra internet — chỉ API qua Ingress/LoadBalancer công khai.
  - **`GET /app`, `GET /admin` và `GET /users/{userId}/ratings` (demo-user-app-personas) phải tắt ở production**: cùng cờ `api.demo_enabled`, trả 404 khi tắt. "Tài khoản" trên trang `/app` là persona demo gắn với userId MovieLens, **không có xác thực**: ai biết URL đều gọi được mọi route demo, và `/users/{userId}/ratings` lộ lịch sử xem phim của bất kỳ userId nào (cùng loại với `/debug/users`). Ở production phải thay bằng đăng nhập thật (mật khẩu băm, session/JWT) và chỉ cho mỗi người xem lịch sử của chính mình — design-only, chưa triển khai.
  - **`POST /movies` và `DELETE /movies/{movieId}` (demo-use-case-scenarios) phải tắt ở production**: đây là route ghi vào danh mục phim không có xác thực, cùng cờ `api.demo_enabled`, trả 404 khi tắt. `DELETE` chỉ nhận id ≥ 9,000,000 nên danh mục MovieLens không xoá được qua API ngay cả khi cờ bật. `GET /debug/system` (model registry, tiến độ retrain) cũng nằm sau cờ này.
  - **`GET /demo` và `GET /debug/users/{userId}` (add-demo-web-client) phải tắt ở production**: `configs/serving.yaml: api.demo_enabled` mặc định `false`, cả 2 route trả 404 khi tắt (đã implement, verified — xem `evidence/p2_demo_ui.txt`). Lý do: `/debug/users/{userId}` lộ lịch sử xem phim của user (`recent_movieIds`, `positive_movieIds`) theo `userId` không cần xác thực — `userId` tuy đã ẩn danh theo PRD nhưng route này vẫn là một cách liệt kê hành vi user không nên mở công khai. Route chỉ bật thủ công, tạm thời, cho buổi demo.

### 2.7 Trade-off chi phí/hiệu năng: batch loader "recompute toàn bộ" vs "incremental"

**Quan sát đo được**: `loaders.build_user_state` (task 3.3) tính lại **toàn bộ** `user_history`
từ `user_history_seed.parquet` mỗi lần chạy — mất khoảng 11 phút cho 32,000,204 dòng /
200,948 user trên 1 máy `local[*]`. Chi phí này lặp lại mỗi lần retrain (B6), kể cả khi
chỉ có vài trăm rating mới.

| Phương án | Chi phí | Độ phức tạp | Rủi ro |
|---|---|---|---|
| **A. Recompute toàn bộ** (đang dùng) | O(toàn bộ dữ liệu) mỗi lần; ~11 phút/32M dòng, tuyến tính theo executor | Thấp — 1 job, không cần theo dõi state gia tăng | An toàn tuyệt đối: không có class lỗi "quên cập nhật 1 phần" |
| B. Incremental (chỉ update user bị ảnh hưởng) | O(số user thay đổi) — `serve_batch` đã làm cách này cho streaming (mục 6.5) | Cao hơn — cần theo dõi "user nào thay đổi từ lần chạy trước" | Rủi ro state trôi (drift) nếu bỏ sót 1 batch |

**Quyết định**: giữ phương án A cho batch loader định kỳ (chạy khi có M2 handoff mới, tần suất thấp — không phải mỗi request), vì đơn giản và không có rủi ro drift; dùng phương án B (đã implement) riêng cho đường streaming realtime, nơi latency thấp là bắt buộc và chỉ có 1 user thay đổi mỗi event. Đây đúng tinh thần "batch xử lý lịch sử lớn, streaming xử lý cập nhật nhỏ tức thời" của kiến trúc gốc (`docs/ARCH.txt` §1: "Batch xử lý lịch sử lớn; Streaming tiếp nhận rating mới").
Nếu M2 handoff tần suất tăng (ví dụ retrain hàng giờ thay vì hàng ngày), nên chuyển sang phương án B kèm cơ chế watermark tương tự `pipeline_state` đã có cho streaming.

### 2.8 Trade-off kiến trúc: API vừa đọc vừa ghi (`add-demo-web-client`)

**Quyết định hiện tại (đã implement, demo scope)**: `POST /ratings` và `GET /ratings/{eventId}`
nằm chung 1 FastAPI process với `GET /recommendations/{userId}` (design.md D-1 của
`add-demo-web-client`) — cùng container `api`, cùng port, không thêm hạ tầng.

| Phương án | Ưu điểm | Nhược điểm |
|---|---|---|
| **A. Chung 1 service** (đang dùng) | Không thêm container/config cho demo; triển khai 1 lệnh `docker compose up` | Đường đọc và đường ghi có đặc tính scale khác nhau (đọc: nhiều, latency thấp, không trạng thái; ghi: ít hơn, phụ thuộc Kafka còn sống) nhưng bị trói vào cùng 1 tiến trình — không thể scale/deploy độc lập, và 1 pod bị OOM vì ghi cũng kéo sập đường đọc |
| B. Tách "rating ingestion service" riêng | Đúng hướng production: scale độc lập, có thể đặt rate-limit/auth riêng cho đường ghi mà không ảnh hưởng đường đọc; lỗi ở service ghi không bao giờ chạm tới service đọc | Thêm 1 container/Deployment, thêm service discovery, thêm CI/CD pipeline — không đáng cho phạm vi demo môn học |

**Vì sao vẫn chấp nhận được ở dev/demo**: thiết kế đã cô lập rủi ro bằng cách khác — producer
Kafka được tạo **lười** (`get_producer()`, tạo ở request `POST /ratings` đầu tiên) và **không**
có `depends_on: kafka` cứng (design D-7), nên Kafka chết chỉ làm `POST /ratings` trả 503, đường
đọc `GET /recommendations` không bị ảnh hưởng (verified — `evidence/p2_demo_rating_api.txt` Test 3).
Đây là cách giảm bớt nhược điểm của phương án A mà không cần tách service.

**Phim demo chỉ nằm trong MongoDB (demo-use-case-scenarios, design D-10)**: `POST /movies` ghi
thẳng vào collection `movies`, không vào `curated_movies` (Parquet) vì API không có Spark, và ghi
Parquet từ API sẽ ghi đồng thời với Spark. Trong production, thêm phim vào danh mục đi qua batch ETL
vào `curated_movies` rồi nạp lại Mongo; route này chỉ là lối tắt demo. Hệ quả cần biết:
- Rating cho phim demo vẫn được streaming append vào `curated_ratings` như mọi rating, nên
  `curated_ratings` có thể chứa `movieId` ≥ 9,000,000 không có trong `curated_movies`. Job retrain
  (Person 1) phải bỏ qua hoặc chấp nhận các id này.
- `bootstrap_registry` kiểm tra `movies == 87,585` nên phải xoá phim demo trước khi nạp lại.
- Xoá phim không xoá rating đã gán; id phim demo cấp từ bộ đếm chỉ tăng nên không bao giờ dùng lại.
- Phim mới không nằm trong `similar_movies` (tính sẵn theo version), nên được ghép theo thể loại và
  chèn vào vị trí dành riêng (xem `docs/SERVING_ARCHITECTURE.md` §2). Production sẽ tính độ tương tự
  cho phim mới ở lần retrain tiếp theo.

**Hướng production**: tách thành 1 Deployment/service riêng (`rating-ingestion`), chỉ giữ trách
nhiệm validate + produce Kafka, scale theo throughput Kafka producer thay vì theo lưu lượng đọc.
`GET /ratings/{eventId}` có thể ở lại service đọc (chỉ là 1 point-read Mongo) hoặc đi cùng
service ghi — cả hai đều hợp lý, chưa cần quyết định cho tới khi có số liệu tải thật.

## 3. CAP / Consistency (đề bài §Minimum technical requirements: NoSQL data modeling/CAP)

| Dữ liệu | Mô hình consistency | Lý do |
|---|---|---|
| `serving_meta` (con trỏ active version) | **Strongly consistent** (đọc/ghi trên primary Mongo) | Đây là nguồn duy nhất quyết định version nào đang phục vụ — không được phép có 2 giá trị mâu thuẫn cùng lúc; MongoDB đảm bảo atomic ở mức 1 document |
| `user_history` / `user_rated` (cập nhật bởi streaming) | **Eventually consistent** với hành vi thật của user | Một request ngay sau khi rate có thể (hiếm) chưa thấy rating mới nếu batch streaming chưa commit (trigger 5 giây) — chấp nhận được, đã disclose trong PRD §15 "User History serving state cập nhật từ validated rating events" |
| `user_recommendations`/`similar_movies`/`popular_movies` | **Immutable theo version** | Mỗi version là bất biến sau khi nạp xong; không có ghi đè giữa chừng — nhất quán tự nhiên vì đọc luôn theo cặp (collection, modelVersion) cố định |

**Trade-off CAP cụ thể**: khi Mongo mất kết nối tới primary (network partition), thiết kế
hiện tại chọn **AP cho đường online serving** (API vẫn cố gắng trả lời, có thể dùng dữ liệu
hơi cũ nếu đọc từ secondary với `readPreference=secondaryPreferred`) nhưng **CP cho việc ghi
`serving_meta`** (promotion gate không được phép activate version mới nếu không ghi được vào
primary — thà giữ nguyên version cũ còn hơn có 2 API instance phục vụ 2 version khác nhau).
Đây là lý do `promotion_gate.py` coi bất kỳ lỗi ghi nào là FAIL an toàn (mục 2.4), không retry
ngầm rồi âm thầm bỏ qua.
