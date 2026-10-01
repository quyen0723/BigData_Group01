## Context

**Hiện trạng**
- Person 1 (Quyên) đã hoàn tất Phase 1–3 và M2 handoff:
  - Curated Parquet (`curated_ratings` partition theo `year`, 32,000,204 dòng).
  - 3 serving artifact: `popular_movies.json` (1 object, 10 items), `similar_movies.json` (array, ~80.5k docs, 82 MB), `als_topn.json` (array, 154,608 docs, 94 MB).
  - `user_history_seed.parquet` (32M dòng `userId, movieId, rating, rating_ts`), model `als_v1.0.0` (Spark ML) và `model_card.json`.
  - Tất cả nằm trên Drive (`movielens32m/`); repo chỉ có `popular_movies.json` và `model_card.json`.
- Contract đóng băng ở `contracts/CONTRACTS.md`:
  - §3: 4 schema serving.
  - §4: routing tiers, T tunable.
  - §5: rating event.
  - §6: version rules. Activate phải atomic; fail thì bản cũ tiếp tục phục vụ.
- Toàn bộ phần của Person 2 chưa có code.

**Ràng buộc**
- Máy dev: Windows 11, 31.7 GB RAM, Java 21, Python 3.12.10. Docker Desktop đã cài nhưng chưa chạy. System Python chưa có pyspark/pymongo.
- Person 1 pin `pyspark==3.5.7`. Đề bài yêu cầu PySpark DataFrame API, NoSQL read-back, Structured Streaming path tối thiểu, và tách rõ Implemented / Design-only.
- Dữ kiện đã đo được:
  - Mọi user seed có ≥ 20 ratings (EDA: min 20, max 33,332, median 73).
  - 46,340 user không có doc ALS (`coldStartStrategy='drop'`, chỉ có rating sau `cut_test`).
  - `als_topn` đã loại **toàn bộ** phim từng rate trong curated.
- Lịch: M3 (29/09), M4 (30/09), M5 (30/09), 7.2 (01/10), 8.1 (02/10), 8.2 (03/10).

**Ranh giới trách nhiệm** (tracker 6.1/6.2, `PLAN_Person1.md` B6)
- Person 1 train ALS candidate (Colab), tính metrics và xuất artifact candidate.
- Person 2 phụ trách trigger, bàn giao dữ liệu mới, import candidate, chạy gate, activate/rollback và test fail/pass.

## Goals / Non-Goals

**Goals:**
- Chạy lại được toàn bộ phần online bằng một chuỗi lệnh từ trạng thái sạch (Docker Compose + bundle `movielens32m/`).
- MongoDB serving store đúng contract §3, index theo access pattern, có read-back + `explain()` làm evidence.
- API trả Top-N đúng tier, **không bao giờ** trả phim user đã rate, luôn có `modelVersion`.
- Rating event đi Kafka → Structured Streaming → Curated Parquet + `user_history`, idempotent theo `eventId`, phục hồi được từ checkpoint.
- Vòng đời model: candidate chỉ phục vụ khi qua gate; fail thì active version không đổi; có rollback.
- T được chọn bằng thí nghiệm có quy tắc quyết định viết trước khi chạy.
- Đủ evidence cho rubric: NoSQL, Streaming, Deployment design, Validation, Demo.

**Non-Goals:**
- Train/tune ALS, sửa split hay metric offline (thuộc Person 1).
- Online learning ALS theo từng event (ARCH §10 đã loại trừ).
- Policy / eligibility filter (design-only: MovieLens không có dữ liệu tuổi).
- Triển khai cluster/cloud thật hoặc HA (chỉ làm tài liệu design).
- Auth/UI cho API; ANN/vector search.

## Decisions

### D-1. Runtime: Docker Compose, Spark chạy `local[*]` trong container

Các service:

| Service | Image / cấu hình | Ghi chú |
|---|---|---|
| `mongo` | single node, `--wiredTigerCacheSizeGB 3`, volume `mongo-data` | |
| `kafka` | `apache/kafka` KRaft, 1 broker | Listener nội bộ cho container, listener host cho producer chạy ngoài |
| `spark` | image tự build: `python:3.12-slim` + OpenJDK 17 + `pip install pyspark==3.5.7` | Trùng bản PySpark với Person 1; Java 17 là bản Spark 3.5 hỗ trợ chính thức |
| `api` | `python:3.12-slim` + FastAPI/uvicorn, không có Java | |

- Spark packages (`spark-sql-kafka-0-10_2.12:<spark-version>`, `mongo-spark-connector_2.12:10.x`) resolve qua `spark.jars.packages` và cache ở volume ivy. Lần chạy đầu cần internet.
- Tag image và version package được pin khi setup, ghi vào `evidence/p2_env_versions.txt`.
- Ngân sách RAM, tính theo giới hạn mặc định của WSL2 ≈ 50% RAM host (~15.8 GB): Mongo 3 GB cache, Spark driver 6–8 GB, Kafka ~1 GB, API < 0.5 GB. Có thể nâng qua `.wslconfig` nếu cần.
- **Phương án đã cân nhắc:**
  - Native Windows: cần winutils/hadoop.dll, khó tái lập.
  - Hybrid (Mongo + Kafka trên Docker, Spark native): vẫn vướng winutils.
  - Colab: không host được Kafka/Mongo lâu dài.
- **Trung thực:** Spark local mode nghĩa là driver = executor trong 1 JVM. Việc ánh xạ sang cluster được mô tả ở `docs/DEPLOYMENT_DESIGN.md`.

### D-2. Vị trí dữ liệu: bundle `movielens32m/` ở gốc repo (đã gitignore), mount vào `/data`

```
movielens32m/
├── curated/curated_ratings/   ← append target của stream (bản copy local của curated trên Drive)
├── curated/curated_movies/
├── artifacts/                 ← 3 JSON + user_history_seed.parquet
├── models/als_v1.0.0/
├── candidates/<version>/      ← Person 1 trả candidate về đây
└── stream/{raw_events, quarantine, checkpoints/{raw,valid,invalid}, handoff}
```

Mọi path nằm trong `configs/serving.yaml` và `configs/streaming.yaml`, không hardcode trong source (theo quy ước README).

### D-3. Nạp artifact bằng Spark + mongo-spark-connector, không dùng `mongoimport`

- Đọc bằng `spark.read.option("multiLine", True).schema(<explicit>).json(path)`:
  - File array cho ra 1 dòng mỗi phần tử.
  - `popular_movies.json` (1 object) cho ra 1 dòng.
  - Không để Spark tự infer schema, giống quy ước của Person 1.
- Validate `modelVersion` của file khớp tham số `--version`. Lệch thì dừng.
- Idempotent: `deleteMany({modelVersion: v})` trên collection đích rồi insert. Chạy lại cho cùng kết quả.
- `movies`, `user_rated`, `user_history` sinh từ Parquet bằng Spark, ghi bằng connector. Đây là evidence "Spark output written to NoSQL".
- **Phương án đã cân nhắc:**
  - `mongoimport --jsonArray`: MongoDB ghi rõ giới hạn 16 MB; file popular lại không phải array.
  - pymongo `insert_many`: được, nhưng không có evidence phân tán. Chỉ dùng pymongo ở streaming, vì cần update operator (`$max`, pipeline update) mà connector không hỗ trợ.

### D-4. Data model MongoDB: 4 collection theo contract + 6 collection additive

| Collection | Khoá / index | Access pattern | Số lượng | Ghi bởi | Loại |
|---|---|---|---|---|---|
| `popular_movies` | unique `(scope, modelVersion)` | `findOne({scope:"global", modelVersion})` | 1 / version | loader | contract §3.1 |
| `similar_movies` | unique `(movieId, modelVersion)` | `find({movieId:{$in:seeds}, modelVersion})` | ~80.5k / version | loader | contract §3.2 |
| `user_recommendations` | unique `(userId, modelVersion)` | `findOne({userId, modelVersion})` | 154,608 / version | loader | contract §3.3 |
| `user_history` | unique `userId` | `findOne({userId})`; stream update | 200,948 + user mới | loader, stream | contract §3.4 |
| `movies` | `_id = movieId` | `find({_id:{$in:ids}})` để enrich / tie-break | 87,585 | loader | additive |
| `user_rated` | unique `(userId, movieId)` | `find({userId, movieId:{$in:cands}}, {movieId:1,_id:0})` (covered) | ~32M | loader, stream | additive |
| `rating_events` | `_id = eventId` | ledger dedup, export delta theo `ingestedAt` | tăng dần | stream | additive |
| `serving_meta` | `_id = "active"` | đọc con trỏ active (cache TTL) | 1 | orchestrator | additive |
| `model_registry` | `_id = modelVersion` | audit trạng thái, gate report | vài doc | orchestrator | additive |
| `pipeline_state` | `_id = "ratings_stream"` / `"retrain_handoff"` | commit `batchId`, watermark handoff | 2 | stream, orchestrator | additive |

**Embedding hay referencing** (để biện minh trong report §10)
- Danh sách Top-N/similar được **embed** vì mảng bị chặn (N = 10, M = 20, popular ≤ 100): 1 lần đọc là đủ.
- Tập phim đã rate được **reference**, mỗi cặp (user, phim) 1 doc trong `user_rated`, vì:
  - Không bị chặn: user lớn nhất có 33,332 ratings. Đây là anti-pattern "unbounded arrays" mà ARCH trích dẫn.
  - Query `$in` trên index `(userId, movieId)` là *covered query*, chỉ trả phần giao với tập ứng viên.

**`user_history`** giữ đúng schema §3.4 với các mảng bị chặn:
- `recent_movieIds` tối đa R = 50: mới nhất theo `rating_ts`, tie-break `movieId`.
- `positive_movieIds` tối đa P = 50: rating ≥ 4.0, mới nhất trước.
- `interaction_count` = số **phim khác nhau** đã rate. Định nghĩa này khớp khoá unique `(userId, movieId)` của curated; seed cho `Σ interaction_count = 32,000,204`.

**Contract**
- Không đổi schema doc; các collection additive không ảnh hưởng consumer hiện có.
- Điểm cần Person 1 ký: trong giai đoạn staging, `user_recommendations` chứa nhiều version nên 1 doc cho mỗi `(userId, modelVersion)`.

### D-5. Version hoá + activate atomic qua con trỏ `serving_meta`

```
serving_meta { _id:"active", modelVersion:"v1.0.0", previousVersion:null, activatedAt,
               artifacts:{ user_recommendations:"v1.0.0", similar_movies:"v1.0.0",
                           popular_movies:"v1.0.0" }, gateReport:"<id>" }
model_registry { _id:"v1.1.0", status: staged|active|rejected|retired,
                 modelCard:{...}, gateReport:{...}, importedAt, activatedAt }
```

- API đọc con trỏ (cache TTL 5 giây, cấu hình được) rồi query từng collection theo version tương ứng trong `artifacts`.
  - Mỗi request đọc con trỏ **1 lần**, nên mọi phần của một response luôn thuộc cùng một version.
  - Map `artifacts` riêng cho từng collection cho phép candidate chỉ thay artifact nào phụ thuộc model (ARCH §7.6). Ví dụ `similar_movies` chỉ dựa trên genres nên có thể giữ bản cũ.
- Activate: 1 lệnh `updateOne` trên 1 document. MongoDB đảm bảo atomic ở mức single-document, nên không có trạng thái nửa cũ nửa mới.
  - Rollback: gán con trỏ về `previousVersion`.
  - Retention: giữ active + previous; lệnh `cleanup` xoá docs của version đã `retired`.
- **Phương án đã cân nhắc:**
  - `renameCollection`: không atomic khi phải đổi 3 collection cùng lúc.
  - Collection đặt tên theo version: đổi tên collection trong contract.
  - Multi-document transaction: cần replica set, và không cần thiết khi con trỏ là 1 doc.

### D-6. Router + chuỗi hạ cấp

```
c    = user_history[u].interaction_count  (không có doc ⇒ 0)
tier = 0_history (c=0) | few_history (1 ≤ c < T) | enough_history (c ≥ T)
seeds = positive_movieIds[:S] (rỗng ⇒ recent_movieIds[:S]);  S = 10

0_history      : [popular w=1.0]                               strategy=POPULARITY
few_history    : [content(seeds) w=1.0, popular w=β_p]        strategy=CONTENT+POPULARITY
enough_history : [ALS[u] w=1.0, content(seeds) w=β_c]         strategy=ALS+CONTENT
   ALS doc không có  ⇒ xử lý như few_history, fallbackReason="als_artifact_missing"
   content rỗng      ⇒ bỏ nguồn đó,           fallbackReason="no_content_candidates"
   sau fusion < k     ⇒ lấp bằng popular,     fallbackReason="filled_from_popularity"
```

- Chuỗi hạ cấp ALS → Content → Popularity bao trọn 46,340 user cold-start. Họ có lịch sử nên nhận gợi ý content thay vì popularity thuần.
- Cách này tương thích contract §4, vì `similar_movies` vốn là nguồn bổ sung của tier Enough.
- `fallbackReason` ghi vào cả response và log để đo fallback rate.
- `T`, `S`, `β_c`, `β_p` là **tham số thiết kế** trong `configs/serving.yaml`:
  - T chọn bằng D-11.
  - β đặt mặc định 0.3 và ghi rõ là chưa tune (ARCH §6.10).
- Giá trị T tạm thời trước khi có thí nghiệm là 10, đánh dấu *provisional*. Với seed data, mọi T ≤ 20 đều đưa tất cả user seed vào tier Enough.

### D-7. Exclusion chính xác qua `user_rated`

- Mỗi request có tier ≠ 0 chạy 1 covered query `$in` trên tập ứng viên (≤ ~10 + 20·S + 100 id).
- Tier 0 bỏ qua query này (user không có lịch sử).
- Stream upsert `user_rated`, nên phim vừa rate sau lần precompute cũng bị loại, đúng yêu cầu ARCH §6.8 "fresh-history exclusion".
- Seeds luôn bị loại vì chúng là phim đã rate.
- **Phương án đã cân nhắc:**
  - Chỉ dùng `recent_movieIds`: sót phim rate lâu, vi phạm DoD 4.2.
  - Mảng `rated_movieIds` trong doc: không bị chặn.
  - Bloom filter: xác suất, phức tạp.

### D-8. Fusion: weighted Reciprocal Rank Fusion

- `score(m) = Σ_s w_s / (60 + rank_s(m))`.
- Rank trong nguồn content: nếu một ứng viên xuất hiện ở nhiều seed thì lấy rank nhỏ nhất.
  - Trong một list similar, các phim có cùng cosine được xếp lại theo `movies.support` giảm dần rồi `movieId` tăng dần.
  - Việc này xử lý đúng giới hạn "score 1.0 ties theo scan order" mà MODEL_DESIGN §4 đã ghi.
- Tie-break cuối cùng: `support` giảm dần, rồi `movieId` tăng dần, để kết quả deterministic.
- Chọn RRF vì điểm của các nguồn không cùng thang (ALS là rating dự đoán, content là cosine [0,1], popularity là avg rating). RRF không phụ thuộc thang đo, đúng hướng PRD §21 ("rank-based fusion").
- **Phương án đã cân nhắc:** chuẩn hoá min-max rồi cộng trọng số, nhưng cách này nhạy với outlier và độ dài list.

### D-9. Streaming topology: 3 query, tách bronze và silver

```
producer (confluent-kafka, acks=all, idempotence) ─► topic ratings.v1 (3 partitions, key=userId)
Q1 raw     : readStream kafka ─► (key, value, partition, offset, kafkaTs, ingest_date)
             ─► parquet FILE SINK /data/stream/raw_events (partition ingest_date)   [Raw Event Storage]
             ckpt /data/stream/checkpoints/raw      — exactly-once, thư mục riêng nên _spark_metadata OK
parsed     : readStream parquet raw_events ─► from_json(value, schema §5)
             ─► left join broadcast(movies.movieId) ─► reason = first failing rule | null
Q3 invalid : parsed.filter(reason not null) ─► parquet FILE SINK /data/stream/quarantine (+reason)
Q2 valid   : parsed.filter(reason is null)
             .withWatermark("event_time", "10 minutes").dropDuplicatesWithinWatermark(["eventId"])
             ─► foreachBatch(serve_batch)           ckpt /data/stream/checkpoints/valid
```

- Luật validate:
  - JSON parse được; `eventId` không rỗng; `userId > 0`.
  - `movieId` tồn tại trong `curated_movies`.
  - `rating ∈ {0.5, …, 5.0}`.
  - `0 < timestamp ≤ now + 1 ngày`.
- Session timezone = UTC. `rating_ts = timestamp_seconds(timestamp)`, `year = year(rating_ts)`.
- Trigger `processingTime = 5 seconds`, `maxOffsetsPerTrigger = 5000`.
- Q2 đọc lại raw thay vì đọc thẳng Kafka, để khớp mũi tên S4 → S5 của kiến trúc. Nếu luật validate thay đổi thì replay được từ raw.
- **Phương án đã cân nhắc:** 1 query với `foreachBatch` làm tất cả. Đơn giản hơn nhưng raw mất tính exactly-once và không có stateful dedup theo event-time, một điểm rubric yêu cầu thảo luận.

### D-10. `serve_batch`: ghi idempotent khi `foreachBatch` là at-least-once

```
serve_batch(df, batchId):
  1. batchId ≤ pipeline_state.ratings_stream.lastBatchId      ⇒ return   (batch đã xử lý xong)
  2. loại event có eventId đã nằm trong rating_events              (dedup vượt watermark)
  3. df.write.mode("append").partitionBy("year").parquet(curated_ratings)   ← batch writer, KHÔNG file sink
     cột đúng §2.1: userId, movieId, rating, timestamp, rating_ts (+ year)
  4. user_rated: upsert latest-wins (pipeline update, chỉ ghi đè khi ts mới ≥ ts cũ)
  5. user_history với mỗi user bị ảnh hưởng (1 writer duy nhất ⇒ không có race):
       interaction_count = count(user_rated{userId})          ← tính lại, không dùng $inc
       recent / positive = áp move-to-front theo thứ tự timestamp rồi cắt về R/P;
                           rating < 4.0 thì loại khỏi positive
       lastUpdated = max(cũ, max event_time)
  6. insert rating_events {_id:eventId, …, batchId, ingestedAt}  (ordered=false, bỏ qua duplicate)
  7. pipeline_state.ratings_stream.lastBatchId = batchId
```

**Lập luận idempotency**
- Bước 4–5 idempotent theo thiết kế: tính lại count thay vì `$inc`; chạy lại chuỗi move-to-front cho cùng trạng thái cuối; `max` idempotent.
- Ledger (bước 6) ghi **sau** khi đã áp dụng. Vì vậy event nằm trong ledger đồng nghĩa đã áp dụng xong, và bước 2 lọc bỏ là an toàn.
- Nếu crash giữa bước 3 và 7, batch chạy lại có thể append Parquet **2 lần**. Curated không có `eventId`, nên xử lý bằng **quy tắc latest-wins theo `(userId, movieId)` khi đọc để retrain** (D4 với Person 1). Quy tắc này cũng giải quyết trường hợp user rate lại cùng phim.
- Checkpoint của Q2 cùng `lastBatchId` đảm bảo restart không xử lý lại batch đã commit.

**Tại sao không dùng file sink cho curated**: file sink tạo `_spark_metadata/`. `DataSource.resolveRelation` (Spark 3.5) khi đó dùng `MetadataLogFileIndex`, chỉ liệt kê file của stream, nên 32M dòng lịch sử bị ẩn khỏi mọi batch read.

### D-11. Thí nghiệm chọn T

- **Không dùng `als_topn.json` để đánh giá.** File này đã loại cả phim user rate trong giai đoạn test, nên HitRate trên test bằng 0 theo cấu trúc.
- Chạy Spark local:
  - `ALSModel.load(als_v1.0.0).recommendForUserSubset(users, 50)`, loại các phim đã rate trước `cut_test`, lấy top-10.
  - Content: seeds là positive trước `cut_test` + `similar_movies` (chỉ dựa trên genres nên không leak).
  - Popularity tính lại trên ratings trước `cut_test` (min_support = 100, cùng công thức với Person 1).
- Tập user: có ≥ 1 rating trước `cut_test` **và** ≥ 1 phim relevant (rating ≥ 4.0) sau `cut_test`, **và** có user factor trong ALS. Cả 3 chiến lược được đo trên **cùng tập user này**.
  - Lưu ý phương pháp: `metrics.csv` hiện so ALS (3,956 user) với Popularity (30,011 user) trên hai tập khác nhau.
- Chia bucket theo số tương tác trước `cut_test`: `[1–4] [5–9] [10–19] [20–49] [50–99] [100+]`. Đo HitRate@10 và NDCG@10, kèm n và khoảng tin cậy 95% (bootstrap).
- **Quy tắc quyết định, chốt trước khi chạy:** T = cận dưới của bucket nhỏ nhất mà từ đó trở lên, HitRate@10 của ALS ≥ Content ở mọi bucket.
  - Không bucket nào thoả: T = cận dưới của bucket cao nhất, ghi rõ.
  - Mọi bucket đều thoả: T = 1.
  - Nếu Popularity thắng ở mọi bucket thì báo cáo trung thực và ghi đề xuất tăng β_p.
- Output: `evidence/p2_tier_threshold.csv` và mục "Ngưỡng T" trong `docs/MODEL_DESIGN.md` (phối hợp Person 1).

### D-12. Retraining orchestration: trigger, bàn giao, import staged, gate, activate

1. **Trigger** (`retrain_trigger`):
   - Điều kiện: `count(rating_events.ingestedAt > watermark) ≥ N_min` (config; demo đặt nhỏ, ví dụ 50), hoặc `--force`, hoặc chạy theo lịch với `--interval`.
   - Trong production sẽ dùng Airflow (design-only).
2. **Handoff package** tại `stream/handoff/<requestId>/`:
   - `delta_ratings.parquet`: schema curated §2.1, lấy các event đã áp dụng có `ingestedAt` trong cửa sổ.
   - `manifest.json`: requestId, activeVersion, proposedVersion, cutoff, số dòng, số user/user mới, max event ts, quy tắc latest-wins, checksum.
   - Cập nhật `pipeline_state.retrain_handoff.watermark`.
   - Kênh mặc định: upload thủ công lên Drive `movielens32m/handoff/` (D2).
3. **Person 1** train rồi trả `candidates/<version>/` gồm `als_topn.json` (+ artifact khác nếu tái sinh), `model_card.json` (có training window + manifest id) và `models/als_<version>/`.
4. **Import staged**: loader D-3 với `--version <v> --stage`. Docs được ghi nhưng không phục vụ, vì con trỏ vẫn giữ nguyên. Registry ghi `status = staged`.
5. **Gate** (`promotion_gate`) tính lại độc lập, không tin số tự khai trong model_card: `ALSModel.load()` cả active và candidate, rồi `transform` trên **cùng holdout** (curated `timestamp ≥ cut_test`, bỏ id lạ).

   | # | Tiêu chí | Mặc định (chờ Person 1 xác nhận, D3) |
   |---|---|---|
   | G1 | RMSE_cand ≤ RMSE_active × (1 + ε) | ε = 0.01 |
   | G2 | RMSE_cand < RMSE_MovieMean_test | 0.9939 (từ model_card) |
   | G3 | RMSE_cand trong band sanity | [0.6, 1.1] |
   | G4 | 100% doc staged đúng schema §3.3; rank 1..n; n ≤ 10; không trùng userId | — |
   | G5 | 0 phim đã rate: rec staged anti-join (curated base ∪ delta) = 0 (Spark, kiểm toàn bộ) | — |
   | G6 | Số user có rec của candidate ≥ của active | — |
   | G7 | semver > active, cùng MAJOR, version chưa từng dùng | — |

6. **PASS**: registry candidate → `active`, bản cũ → `retired`. Con trỏ cập nhật trong 1 lệnh `updateOne`. Ghi evidence trước/sau.
   **FAIL**: registry → `rejected` kèm report. Con trỏ **không bị ghi**. Evidence chứng minh con trỏ trước/sau giống hệt.
7. **Rollback**: `promotion_gate --rollback` gán con trỏ về `previousVersion` nếu docs của nó còn tồn tại.

- **Demo fail-path phải thật, không giả số:** Person 1 train thêm một candidate cố ý kém (ví dụ `maxIter = 1`, `rank = 2`) để G1 fail tự nhiên.
- Mỗi candidate có version riêng; version đã bị reject không dùng lại.

### D-13. Quan sát (observability) và evidence

- API ghi log JSON-lines (`logs/api.jsonl`): `userId, tier, strategy, fallbackReason, modelVersion, k, n_returned, latency_ms`.
- Script tổng hợp tính: phân bố strategy, fallback rate, latency p50/p95 trên tải thử khoảng 1,000 request qua các tier.
- Streaming ghi `query.lastProgress` (input/processed rows per sec, batch duration, watermark).
- Mọi evidence nằm ở `evidence/p2_<wbs>_<tên>.txt|csv`, theo quy ước của Person 1.

### D-14. Chiến lược test

- **Unit** (pytest, không cần Docker): router, fusion, exclusion và update `user_history` là hàm thuần. Fixture lấy từ `contracts/samples/`.
- **Integration** (`-m integration`): chạy trên stack compose với Mongo + API thật.
- **Test matrix 7.2** chạy bằng script, mỗi case ghi evidence:
  - event không hợp lệ;
  - user không tồn tại;
  - exclusion khi artifact đã cũ;
  - replay `eventId`;
  - kill/restart streaming;
  - thiếu doc ALS;
  - `k` ngoài biên;
  - gate FAIL, gate PASS, rollback.
- **Demo E2E** chạy bằng script, dùng user mới `300001` đi qua tier 0 → Few → Enough, gate FAIL rồi PASS.

### D-15. Tài liệu bàn giao

- `docs/DEPLOYMENT_DESIGN.md` (design-only):
  - Spark trên Kubernetes hoặc dịch vụ managed (Dataproc/EMR): vị trí driver/executor.
  - Object storage cho curated/raw/checkpoint.
  - MongoDB replica set, shard theo hashed `userId`.
  - Kafka RF = 3, số partition theo throughput.
  - API stateless, scale ngang.
  - Observability, bảo mật (secret manager, TLS, least privilege), 1 trade-off chi phí/hiệu năng (trigger interval và chi phí; spot executors cho retrain).
  - Thảo luận CAP / consistency: `user_history` eventually consistent với curated; con trỏ version strongly consistent trên primary.
- Sơ đồ kiến trúc có đánh dấu **Implemented / Design-only** cho từng block.
- `CHECKLIST_Person2.md`, run sequence trong README, tài liệu nguồn cho report §10–§12.

## Risks / Trade-offs

- **[RAM Docker không đủ khi nạp 32M `user_rated`]** → Ghi theo batch qua connector, giới hạn cache Mongo 3 GB, nâng memory WSL2 nếu cần. Phương án B: bỏ `user_rated` cho seed, dựa vào exclusion lúc precompute + `recent_movieIds`, và ghi rõ exclusion không còn chính xác tuyệt đối.
- **[Lần chạy đầu cần internet để kéo image và Spark packages]** → Pin version; cache ivy trong volume; hướng dẫn chuẩn bị trước buổi demo.
- **[Bàn giao qua Drive thủ công, chậm]** → Rubric cho phép demo từ "prepared reproducible runs". Chuẩn bị sẵn candidate PASS/FAIL trước buổi demo.
- **[Person 1 chậm với D1–D4]** → Mọi quyết định có default ghi trong design, nên code không bị chặn. Riêng D1: `popular` chỉ 10 items thì response có thể trả < k, ghi `fallbackReason` và cảnh báo.
- **[β và S chưa được tune]** → Ghi rõ là tham số thiết kế. Có thể thêm kiểm tra độ nhạy (sensitivity) nếu còn thời gian.
- **[Thí nghiệm T có thể cho thấy Popularity thắng ở mọi bucket]** → Quy tắc quyết định chốt trước; báo cáo trung thực, không chỉnh lại quy tắc sau khi thấy kết quả.
- **[Mongo và Kafka single-node, không có HA]** → Đúng phạm vi course. HA/sharding mô tả trong DEPLOYMENT_DESIGN; CAP được thảo luận trong report.
- **[Read-modify-write theo từng user trong `serve_batch` không scale]** → Chấp nhận ở quy mô demo. Tài liệu hoá hướng scale: pipeline update phía server, partition theo userId.
- **[Lệch timezone ở ranh giới năm]** → Curated của Person 1 tính `year` theo session timezone local, stream dùng UTC. Ảnh hưởng không đáng kể; ghi chú trong report.
- **[Con trỏ cache TTL]** → Mỗi request nhất quán trong chính nó. Giữa các request, có tối đa 5 giây trước khi thấy version mới; chấp nhận được.
- **[Cửa sổ dữ liệu retrain]** → Nếu candidate train cả dữ liệu trong holdout thì G1–G3 bị leak. Cần chốt với Person 1 (D3).

## Migration Plan

1. `docker compose up -d`, rồi khởi tạo index (script idempotent).
2. Bootstrap `v1.0.0`:
   - Nạp `movies`, `user_rated`, `user_history` từ Parquet.
   - Nạp 3 artifact với `--version v1.0.0`.
   - Chạy gate ở chế độ bootstrap: chỉ G4–G7, vì chưa có version active để so sánh.
   - Activate. Con trỏ = `v1.0.0`.
3. Kiểm tra read-back (count khớp nguồn, query mẫu, `explain`) và ghi evidence.
4. Khởi động API, rồi 3 query streaming, rồi producer.
5. Vòng refresh: trigger → handoff → Person 1 train → import staged → gate → activate hoặc giữ nguyên.
6. **Rollback:** lệnh rollback con trỏ; dừng stream (checkpoint đảm bảo chạy tiếp đúng chỗ); `docker compose down -v` để reset hoàn toàn.

## Open Questions

- **D1** (Person 1): xuất lại `popular_movies` top-100, schema giữ nguyên, 1 object `scope: global`?
- **D2** (Person 1): kênh bàn giao delta và candidate. Mặc định là thư mục Drive `movielens32m/handoff/` và `movielens32m/candidates/<version>/`, upload/tải thủ công.
- **D3** (Person 1): ngưỡng gate (ε, band) và **cửa sổ dữ liệu train của candidate**. Đề xuất: train+val ∪ delta, loại cửa sổ holdout để G1–G3 so sánh công bằng. Kèm cách đặt version cho candidate FAIL dùng trong demo.
- **D4** (Person 1): quy tắc latest-wins theo `(userId, movieId)` khi đọc curated để retrain. Rate lại **không** tăng `interaction_count`.
- **D5** (cả nhóm): ai viết report §10–§12 và `DEPLOYMENT_DESIGN.md`. Đề xuất Person 2.
- **D6**: Person 1 ký xác nhận bổ sung contract (1 doc cho mỗi `(userId, modelVersion)` khi staging, cùng các collection additive).
