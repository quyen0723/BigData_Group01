# Kiến trúc Serving, Streaming & Model Refresh (Person 2)

> Nguồn thiết kế: `openspec/changes/person2-serving-streaming-integration/design.md` (D-1 … D-15).
> Contract dữ liệu: `contracts/CONTRACTS.md`. Chi tiết triển khai production: `docs/DEPLOYMENT_DESIGN.md`.
>
> **Cập nhật 2026-09-27**: mọi khối màu xanh lá dưới đây đã **Implemented** — chạy thật trên
> Docker Compose (`docker/docker-compose.yml`), verify bằng dữ liệu M2 thật (200,948 user,
> 32,000,204 rating). Bằng chứng: `evidence/p2_*`, `openspec/changes/person2-serving-streaming-integration/tasks.md`.

**Chú thích màu (dùng chung cho mọi sơ đồ):**

| Màu | Ý nghĩa | Trạng thái |
|---|---|---|
| Xanh dương | Person 1: offline modeling | **Implemented** — xong ở M2 |
| Xanh lá | Person 2: serving/streaming/orchestration | **Implemented** — chạy thật, có evidence (xem ghi chú trên) |
| Vàng | Kho dữ liệu: MongoDB, Kafka, Parquet | **Implemented** |
| Xám, viền đứt | Design-only | **Proposed** — chưa triển khai trong phạm vi course (Policy/Eligibility Filter — thiếu dữ liệu tuổi/certification; Airflow scheduler — dùng CLI `--force`/cron thủ công thay thế; cluster/cloud thật — xem `docs/DEPLOYMENT_DESIGN.md` §2) |

---

## 0. Vì sao 2 kho dữ liệu: Curated Parquet vs MongoDB

> Trả lời trực tiếp câu hỏi review: *"Architecture chưa mô tả rõ cách data được lưu
> xuống DB như thế nào?"* — trước khi đi vào chi tiết từng sơ đồ, cần hiểu **vì sao
> có 2 kho** và **kho nào chứa gì**. `docs/ARCH.txt` (kiến trúc gốc) đã nêu nguyên tắc
> này: *"MongoDB là Serving Store, không phải training store. Curated Parquet là
> nguồn phân tích/huấn luyện; MongoDB tối ưu cho read path theo userId/movieId."*

Hai kho phục vụ hai cách đọc dữ liệu khác nhau — dùng chung 1 kho cho cả 2 việc sẽ
chậm ở ít nhất 1 phía:

| | Curated Parquet | MongoDB |
|---|---|---|
| Mục đích | Phân tích + huấn luyện (Spark SQL, MapReduce, train ALS) | Phục vụ trực tiếp (API trả lời user) |
| Cách đọc điển hình | Quét **toàn bộ** dữ liệu (32,000,204 dòng) | Tra **đúng 1 bản ghi** theo `userId`/`movieId` |
| Tốc độ chấp nhận được | Vài giây → vài phút (chạy nền, không ai chờ) | Vài mili-giây (user đang chờ) |
| Ai ghi | Person 1 (ETL gốc) + Person 2 (streaming ghi thêm) | Chỉ Person 2 |

```mermaid
flowchart TB
  CSV["MovieLens CSV<br/>(1 lần, lịch sử)"] --> CUR
  RATE["User rate 1 phim"] --> KAFKA[["Kafka"]] --> SS["Structured Streaming"]

  subgraph CURP["Curated Parquet — kho phân tích/huấn luyện (Person 1)"]
    CUR[("curated_ratings<br/>32,000,204 dòng gốc<br/>+ phần Person 2 ghi thêm")]
  end

  SS -->|"append (batch writer)"| CUR
  SS -->|"cập nhật NGAY"| MONGO

  CUR -->|"Spark SQL · MapReduce ·<br/>train ALS (offline, chạy nền)"| RESULT["Kết quả tính sẵn:<br/>3 file JSON + model"]
  RESULT -->|"nạp (Spark Connector)"| MONGO

  subgraph MONGO["MongoDB — kho phục vụ (Person 2)"]
    direction TB
    M1[("user_recommendations<br/>similar_movies · popular_movies")]
    M2[("user_history · user_rated")]
  end

  MONGO -->|"API CHỈ đọc từ đây<br/>không bao giờ đọc thẳng Parquet"| RESP["Trả gợi ý cho User"]

  classDef p1 fill:#e7f0ff,stroke:#3b6fd8,color:#0b2a66
  classDef p2 fill:#e9f7ec,stroke:#2f8f46,color:#0f3d1c
  classDef store fill:#fff4d6,stroke:#c98a00,color:#4a3300
  classDef actor fill:#fde8e8,stroke:#c0392b,color:#5c1111
  class CSV,CUR,RESULT p1
  class SS,RESP p2
  class KAFKA,M1,M2 store
  class RATE actor
```

**Điểm dễ hiểu nhầm nhất**: khi user rate 1 phim, dữ liệu đi vào **cả 2 kho cùng
lúc** nhưng với 2 tác dụng khác nhau:

1. **Ghi vào MongoDB** (`user_history`, `user_rated`) → có tác dụng **ngay lập
   tức**. Gọi lại API liền sau khi rate là thấy thay đổi (đổi tier, loại phim vừa
   xem khỏi gợi ý).
2. **Ghi thêm vào Curated Parquet** (`curated_ratings`) → **không** có tác dụng
   ngay. Chỉ nằm chờ tới khi Person 2 đóng gói đủ dữ liệu mới gửi cho Person 1
   train lại ALS; gợi ý ALS chỉ đổi sau khi model mới được huấn luyện và duyệt
   qua promotion gate.

Đây chính là nguyên tắc `docs/ARCH.txt` đã ghi: *"Streaming ingestion và ALS
retraining là hai việc khác nhau. Rating mới có thể xuất hiện trong User History
ngay, nhưng chỉ ảnh hưởng latent factors của ALS sau lần Scheduled Retraining kế
tiếp."* MongoDB phản ứng tức thì với hành vi user; model ALS thì học theo lịch,
không học theo từng lần rate.

Chi tiết **MongoDB ghi bằng cơ chế nào** (Spark Connector vs pymongo, insert vs
upsert) xem mục 6 bên dưới.

---


## 1. Tổng thể

```mermaid
flowchart TB
  USER(["USER APP<br/>/app: persona + feed + chấm sao<br/>/admin: quản trị (Implemented, demo-only)"])

  subgraph ONLINE["Online serving & ingestion — Recommendation API (FastAPI)"]
    direction LR
    EP["GET /recommendations/{userId}?k=10"] --> RT["History check + router<br/>0 / Few / Enough + fallback"]
    RT --> EX["Exclude already-rated"] --> FU["Weighted RRF fusion<br/>+ enrich title/genres"]
    EX -.-> POL["Policy filter<br/>(design-only)"] -.-> FU
    PR["POST /ratings<br/>validate + assign timestamp/eventId + produce"]
    ST["GET /ratings/{eventId}<br/>pending / applied lookup"]
  end

  subgraph STREAM["Feedback — Kafka + Spark Structured Streaming"]
    direction LR
    PROD["Producer simulator (CLI)<br/>other non-API producers"] --> KAFKA[["Kafka ratings.v1<br/>key = userId"]]
    PR --> KAFKA
    KAFKA --> Q1["Q1 raw<br/>file sink"] --> RAW[("Raw Event Storage<br/>raw_events/")]
    RAW --> VAL["Validate + dedup eventId<br/>watermark 10 min"] --> SB["Q2 foreachBatch<br/>serve_batch"]
    VAL -->|invalid| QUAR[("quarantine/")]
  end

  subgraph P1H["Person 1 — M2 handoff on Drive (DONE)"]
    direction TB
    ART["Artifacts v1.0.0<br/>popular · similar · als_topn.json"]
    SEED["user_history_seed.parquet<br/>+ curated_movies"]
    MOD["ALS model als_v1.0.0<br/>+ model_card.json"]
  end

  LD["Batch load<br/>Spark + mongo-spark-connector"]

  subgraph MONGO["MongoDB serving store"]
    direction TB
    SM[("serving_meta<br/>active pointer")]
    ARTC[("popular_movies<br/>similar_movies<br/>user_recommendations")]
    UH[("user_history")]
    UR[("user_rated")]
    MV[("movies")]
    OPS[("rating_events<br/>model_registry<br/>pipeline_state")]
  end

  CUR[("Curated Parquet<br/>curated_ratings (year)<br/>Person 1 path")]

  subgraph REFRESH["Feedback & periodic model refresh"]
    direction LR
    AIR["Airflow scheduler<br/>(design-only)"] -.-> TRG["retrain_trigger<br/>N_min / schedule / force"]
    TRG --> HAND["Handoff<br/>delta + manifest"]
    HAND -->|"Google Drive"| TRAIN["Retrain ALS candidate<br/>Person 1 (Colab)"]
    TRAIN -->|"v1.1.0"| IMP["Import candidate<br/>(staged)"]
    IMP --> GATE{"promotion_gate<br/>ALSModel.load + G1..G7"}
    GATE -->|PASS| ACT["Activate<br/>updateOne pointer"]
    GATE -->|FAIL| KEEP["Keep current<br/>v1.0.0 serves"]
  end

  USER <-->|"request / Top-N + modelVersion"| ONLINE
  USER -->|"⭐ rating (demo UI)"| ONLINE
  ONLINE -.->|"read: pointer · history · artifacts · rated · movies"| MONGO
  ST -.->|"read rating_events"| MONGO
  STREAM -->|"upsert user_rated · recompute user_history · ledger"| MONGO
  STREAM -->|"append, batch writer (no file sink)"| CUR
  P1H --> LD -->|"bootstrap v1.0.0"| MONGO
  MONGO -->|"applied events · active version"| REFRESH
  CUR -->|"curated base"| REFRESH
  REFRESH -->|"staged docs · pointer switch"| MONGO

  classDef p1 fill:#e7f0ff,stroke:#3b6fd8,color:#0b2a66
  classDef p2 fill:#e9f7ec,stroke:#2f8f46,color:#0f3d1c
  classDef store fill:#fff4d6,stroke:#c98a00,color:#4a3300
  classDef design fill:#f4f4f4,stroke:#888888,stroke-dasharray: 5 5,color:#555555
  classDef actor fill:#fde8e8,stroke:#c0392b,color:#5c1111
  class ART,SEED,MOD,CUR,TRAIN p1
  class LD,PROD,Q1,VAL,SB,EP,RT,EX,FU,PR,ST,TRG,HAND,IMP,GATE,ACT,KEEP p2
  class KAFKA,RAW,QUAR,SM,ARTC,UH,UR,MV,OPS store
  class POL,AIR design
  class USER actor
```

- **Đường online** (User → API → Mongo): chỉ **đọc** artifact đã precompute, không chạy Spark.
- **Đường ghi rating** (User → API `POST /ratings` → Kafka → Streaming): hộp USER APP là **trang người dùng `/app`** (persona demo, không xác thực, `demo-user-app-personas`) — bấm ⭐ trên trình duyệt đi qua đúng API; trang `/admin` (trang `/demo` cũ, `add-demo-web-client`) là phía quản trị. Cả hai, không đọc/ghi thẳng Mongo hay Kafka. API chỉ xác nhận đã vào Kafka (202), **không** đợi streaming áp dụng — `GET /ratings/{eventId}` cho biết `pending` hay `applied`. CLI `streaming.producer` vẫn là một producer khác, song song, dùng cho kịch bản test không qua API.
- **Đường refresh**: tích luỹ event, bàn giao cho Person 1 retrain, qua gate, rồi đổi con trỏ `serving_meta`.

---

## 2. Luồng request online (Layer 2B)

```mermaid
flowchart TD
  REQ["GET /recommendations/{userId}?k=10"] --> V{"userId > 0 and<br/>1 ≤ k ≤ 50 ?"}
  V -->|no| E422["HTTP 422"]
  V -->|yes| PTR["Read serving_meta (cache 5s)<br/>active version map"]
  PTR --> H["Read user_history<br/>c = interaction_count (no doc ⇒ 0)"]
  H --> T{"c ?"}

  T -->|"c = 0"| T0["Tier 0_history<br/>source: popular_movies"]
  T -->|"1 ≤ c < T"| TF["Tier few_history<br/>content(seeds) w=1.0<br/>+ popular w=β_p"]
  T -->|"c ≥ T"| HAS{"ALS doc for<br/>active version?"}
  HAS -->|yes| TE["Tier enough_history<br/>ALS w=1.0<br/>+ content(seeds) w=β_c"]
  HAS -->|"no — fallbackReason:<br/>als_artifact_missing"| TF

  TF --> SEEDS["seeds = positive_movieIds[:S]<br/>(empty ⇒ recent_movieIds[:S])<br/>similar_movies $in seeds"]
  TE --> SEEDS
  SEEDS --> EXC["Exclude already-rated<br/>user_rated covered $in query"]
  T0 --> FUS
  EXC --> FUS["Weighted RRF fusion<br/>tie-break: support desc, movieId asc"]
  FUS --> FILL{"fewer than k?"}
  FILL -->|"yes — fallbackReason:<br/>filled_from_popularity"| POPF["Fill from popular<br/>(skip rated + duplicates)"]
  FILL -->|no| NEWI
  POPF --> NEWI["new_items (demo, tier few/enough)<br/>phim demo khớp thể loại, bỏ phim đã rate<br/>chèn vào hạng new_items.position, source = new"]
  NEWI --> ENR["Enrich title / genres<br/>from movies"]
  ENR --> OUT["Response<br/>userId · tier · strategy · modelVersion<br/>generatedAt · fallbackReason · recommendations[]"]
  OUT --> LOG[("logs/api.jsonl<br/>tier · strategy · latency")]

  classDef p2 fill:#e9f7ec,stroke:#2f8f46,color:#0f3d1c
  classDef store fill:#fff4d6,stroke:#c98a00,color:#4a3300
  classDef err fill:#fde8e8,stroke:#c0392b,color:#5c1111
  class REQ,PTR,H,T0,TF,TE,SEEDS,EXC,FUS,POPF,NEWI,ENR,OUT p2
  class LOG store
  class E422 err
```

- 46,340 user cold-start (có ≥ 20 ratings nhưng không có doc ALS) đi nhánh `als_artifact_missing` và nhận gợi ý Content, không rơi thẳng về Popularity.
- Exclusion dùng `user_rated` (tập phim đã rate đầy đủ), nên không bỏ sót phim user đã rate từ lâu.
- **Phim mới (`new_items`, change `demo-use-case-scenarios`)**: `similar_movies` được tính sẵn nên phim thêm sau không nằm trong danh sách của phim nào, đường content không bao giờ đưa nó lên. Bước `NEWI` ghép phim demo (id ≥ 9,000,000, `addedAt` trong `window_days`) với hồ sơ thể loại tính từ cùng danh sách seed của nguồn content, rồi **chèn vào một vị trí dành riêng** (mặc định hạng 3, 1 phim) thay vì cộng điểm RRF: với trọng số vừa phải phim mới không thắng nổi doc ALS 10 phim, còn trọng số lớn thì đè lên phim ALS tốt nhất. Tier `0_history` không nhận phim mới. Tắt bằng `new_items.enabled: false` thì kết quả y hệt trước đây.

---

## 3. Streaming pipeline (Layer 1: streaming path)

```mermaid
flowchart TB
  subgraph INGEST["Ingest — Kafka to Spark Structured Streaming (3 queries)"]
    direction LR
    PROD["Producer simulator<br/>scenario · random · invalid · duplicate"] -->|"key = userId"| K[["Kafka ratings.v1<br/>3 partitions"]]
    K --> Q1["Q1 readStream kafka"]
    Q1 -->|"file sink, exactly-once"| RAW[("raw_events/<br/>partition ingest_date")]
    RAW --> P["readStream parquet<br/>from_json(schema §5)<br/>broadcast join movies"]
    P -->|"reason not null"| Q3["Q3 file sink"] --> QU[("quarantine/<br/>+ reason")]
    P -->|valid| W["withWatermark(event_time, 10 min)<br/>dropDuplicatesWithinWatermark(eventId)"]
    W --> Q2["Q2 foreachBatch"]
  end

  subgraph SB["serve_batch(df, batchId) — idempotent, at-least-once safe"]
    direction LR
    S1["1. skip if<br/>batchId ≤ lastBatchId"] --> S2["2. drop eventIds<br/>already in ledger"]
    S2 --> S3["3. append curated_ratings<br/>batch writer, partitionBy year"]
    S3 --> S4["4. upsert user_rated<br/>latest timestamp wins"]
    S4 --> S5["5. recompute user_history<br/>count · recent · positive"]
    S5 --> S6["6. insert rating_events<br/>ledger"]
    S6 --> S7["7. commit<br/>lastBatchId"]
  end

  subgraph SINKS["Sinks"]
    direction TB
    CUR[("curated_ratings<br/>Parquet — Person 1 path")]
    UR[("user_rated")]
    UH[("user_history")]
    LED[("rating_events")]
    PS[("pipeline_state")]
  end

  CK[("checkpoints/<br/>raw · valid · invalid")]
  WARN["No streaming file sink on curated_ratings:<br/>_spark_metadata would hide 32M historical rows"]

  INGEST -->|"micro-batch"| SB
  SB -->|"writes (steps 3–7)"| SINKS
  CK -.-|"offsets + state"| INGEST
  WARN -.- SB

  classDef p2 fill:#e9f7ec,stroke:#2f8f46,color:#0f3d1c
  classDef store fill:#fff4d6,stroke:#c98a00,color:#4a3300
  classDef p1 fill:#e7f0ff,stroke:#3b6fd8,color:#0b2a66
  classDef warn fill:#fde8e8,stroke:#c0392b,color:#5c1111
  class PROD,Q1,P,Q3,W,Q2,S1,S2,S3,S4,S5,S6,S7 p2
  class K,RAW,QU,UR,UH,LED,PS,CK store
  class CUR p1
  class WARN warn
```

- **Idempotency:** bước 4–5 tính lại trạng thái (count, move-to-front, max), không dùng `$inc`. Ledger được ghi **sau** khi đã áp dụng, nên replay một batch không làm lệch `interaction_count`.
- **Parquet bị append trùng khi batch chạy lại:** xử lý bằng quy tắc latest-wins theo `(userId, movieId)` khi đọc để retrain. Quy tắc này cần Person 1 xác nhận (D4).

---

## 4. Vòng đời model: retrain và promotion (Layer 3)

```mermaid
sequenceDiagram
  autonumber
  participant ST as Streaming (serve_batch)
  participant MG as MongoDB
  participant OR as retrain_trigger (P2)
  participant DR as Google Drive
  participant Q as Person 1 (Colab)
  participant GT as promotion_gate (P2)
  participant AP as Recommendation API

  ST->>MG: insert rating_events (ledger)
  OR->>MG: count applied events since watermark
  alt count ≥ N_min or force
    OR->>DR: delta_ratings.parquet + manifest.json
    OR->>MG: advance handoff watermark
  else below threshold
    OR->>OR: log count, no handoff
  end

  Q->>DR: read curated base + delta (latest-wins)
  Q->>Q: retrain ALS, precompute Top-N
  Q->>DR: candidates/v1.1.0 (als_topn, model_card, model)

  GT->>MG: import candidate docs (registry = staged)
  Note over AP,MG: API still serves v1.0.0, pointer unchanged
  GT->>GT: ALSModel.load(active, candidate)<br/>RMSE on same holdout + G1..G7

  alt all criteria PASS
    GT->>MG: updateOne serving_meta to v1.1.0 (atomic)
    GT->>MG: registry: v1.1.0 active, v1.0.0 retired
    AP->>MG: next request reads pointer, serves v1.1.0
  else any criterion FAIL
    GT->>MG: registry: candidate rejected
    Note over MG,AP: serving_meta untouched, v1.0.0 keeps serving
  end
```

- Person 1 train. Person 2 lo trigger, bàn giao, gate và activate/rollback (tracker 6.1/6.2).
- Gate **tính lại RMSE độc lập** bằng `ALSModel.load()` thay vì tin số trong `model_card.json`.

---

## 5. Data model MongoDB (report §10)

```mermaid
erDiagram
  SERVING_META ||--|| MODEL_REGISTRY : "points to active"
  MODEL_REGISTRY ||--o{ USER_RECOMMENDATIONS : "modelVersion"
  MODEL_REGISTRY ||--o{ SIMILAR_MOVIES : "modelVersion"
  MODEL_REGISTRY ||--o{ POPULAR_MOVIES : "modelVersion"
  USER_HISTORY ||--o{ USER_RATED : "userId"
  USER_HISTORY ||--o{ USER_RECOMMENDATIONS : "userId"
  USER_HISTORY ||--o{ RATING_EVENTS : "applied to"
  MOVIES ||--o{ USER_RATED : "movieId"
  MOVIES ||--o{ SIMILAR_MOVIES : "movieId"

  SERVING_META {
    string _id PK "active"
    string modelVersion
    string previousVersion
    object artifacts "per-collection version map"
    date activatedAt
  }
  MODEL_REGISTRY {
    string _id PK "modelVersion"
    string status "staged | active | rejected | retired"
    object modelCard
    object gateReport
  }
  POPULAR_MOVIES {
    string scope UK "unique (scope, modelVersion)"
    string modelVersion UK
    array items "bounded, rank asc"
  }
  SIMILAR_MOVIES {
    int movieId UK "unique (movieId, modelVersion)"
    string modelVersion UK
    array similar "top M = 20"
  }
  USER_RECOMMENDATIONS {
    int userId UK "unique (userId, modelVersion)"
    string modelVersion UK
    string strategy "ALS"
    array recommendations "top N = 10"
  }
  USER_HISTORY {
    int userId UK
    int interaction_count "distinct movies rated"
    array recent_movieIds "cap R = 50"
    array positive_movieIds "rating >= 4.0, cap P = 50"
    date lastUpdated
  }
  USER_RATED {
    int userId UK "unique (userId, movieId)"
    int movieId UK
    float rating "latest wins"
    long ts
  }
  MOVIES {
    int _id PK "movieId"
    string title
    string genres
    int support
  }
  RATING_EVENTS {
    string _id PK "eventId"
    int userId
    int movieId
    float rating
    long timestamp
    long batchId
  }
```

- **Embed:** các danh sách Top-N / similar / popular bị chặn độ dài (10 / 20 / 100), nên chỉ cần 1 lần đọc.
- **Reference:** `user_rated` lưu mỗi cặp (user, movie) là 1 document. Tập phim đã rate không bị chặn (user nhiều nhất có 33,332 ratings); query `$in` trên index `(userId, movieId)` là covered query.
- **Version hoá:** mọi artifact mang `modelVersion`. Chỉ document `serving_meta` quyết định version nào đang được phục vụ, và đổi version là cập nhật 1 document, nên là thao tác atomic.

---

## 6. Cơ chế ghi dữ liệu vào MongoDB — "bằng cách nào", không chỉ "cái gì"

> Các sơ đồ ở §1–§4 cho thấy dữ liệu nào chảy vào Mongo. Mục này trả lời câu hỏi
> hay bị hỏi lại: **công cụ nào thực hiện việc ghi, và ghi theo kiểu gì**. Có
> **3 "người ghi" khác nhau**, cố ý tách riêng vì tần suất và khối lượng dữ liệu
> rất khác nhau — dùng chung 1 cách ghi cho cả 3 sẽ sai ở ít nhất 1 trường hợp
> (xem lý do từng nhánh bên dưới).

```mermaid
flowchart TB
  subgraph W1["Writer 1 — Spark + MongoDB Spark Connector (hàng loạt, theo version)"]
    direction TB
    L1["loaders.build_movies<br/>loaders.build_user_state<br/>loaders.load_artifacts"]
    L1 --> DEL["delete_many({modelVersion: v})<br/>(idempotent: chạy lại không nhân đôi)"]
    DEL --> C1["df.write.format('mongodb')<br/>.option('operationType', 'insert' | 'replace')<br/>.save()"]
    C1 -->|"insert, sau khi xoá version cũ"| M1[("user_recommendations<br/>similar_movies · popular_movies<br/>user_rated · user_history (bootstrap)")]
    C1 -->|"replace, khớp theo _id=movieId"| M2[("movies")]
  end

  subgraph W2["Writer 2 — pymongo trực tiếp (từng batch nhỏ, liên tục)"]
    direction TB
    L2["streaming.pipeline<br/>:: serve_batch(df, batchId)"]
    L2 --> C2["bulk_write([UpdateOne(filter, pipeline)])<br/>upsert=True — $cond so sánh timestamp"]
    C2 -->|"latest-timestamp-wins"| M3[("user_rated")]
    L2 --> C3["tính lại từ đầu (recompute),<br/>KHÔNG dùng $inc"]
    C3 -->|"idempotent với replay"| M4[("user_history")]
    L2 --> C4["insert_many(ordered=False)<br/>bỏ qua lỗi trùng khoá eventId"]
    C4 --> M5[("rating_events<br/>(sổ chống trùng)")]
  end

  subgraph W3["Writer 3 — pymongo trực tiếp (1 document, hiếm khi ghi)"]
    direction TB
    L3["loaders.bootstrap_registry<br/>orchestration.promotion_gate<br/>orchestration.manage_versions"]
    L3 --> C5["replace_one({_id: 'active'}, {...})<br/>1 document = 1 thao tác atomic"]
    C5 --> M6[("serving_meta<br/>model_registry · pipeline_state")]
  end

  classDef writer fill:#e9f7ec,stroke:#2f8f46,color:#0f3d1c
  classDef store fill:#fff4d6,stroke:#c98a00,color:#4a3300
  class L1,DEL,C1,L2,C2,C3,C4,L3,C5 writer
  class M1,M2,M3,M4,M5,M6 store
```

| Writer | Vì sao KHÔNG dùng cách ghi của 2 nhánh còn lại |
|---|---|
| 1. Spark Connector | Ghi bằng `pymongo` từng document một cho 154,608 document `als_topn` sẽ chậm hơn nhiều lần so với Spark ghi song song qua nhiều executor — phù hợp cho khối lượng lớn, chạy 1 lần |
| 2. `pymongo` (streaming) | Cần `upsert` có điều kiện (chỉ ghi đè nếu bản mới hơn) và tính lại `user_history` mỗi lần — Spark Connector chỉ hỗ trợ `insert`/`replace` đơn giản, không biểu diễn được logic "so sánh rồi mới quyết định ghi" này |
| 3. `pymongo` (con trỏ version) | Chỉ 1 document, tần suất cực thấp (vài lần/ngày) — dùng Spark cho việc này là phí tài nguyên (phải khởi động cả cluster Spark chỉ để ghi 1 dòng) |

**Vì sao writer 2 "tính lại toàn bộ" thay vì `$inc`/cộng dồn?** Kafka + Structured
Streaming chỉ đảm bảo **at-least-once** (một batch có thể được xử lý lại nếu job
crash giữa chừng) — nếu dùng `$inc` thì crash 1 lần là `interaction_count` bị
cộng sai. Tính lại từ `user_rated` (đã upsert theo `(userId, movieId)`) đảm bảo
xử lý lại 5 lần hay 1 lần đều ra kết quả giống hệt nhau — **đã verify thật**:
gửi trùng 1 sự kiện 3 lần, `interaction_count` không đổi (`evidence/p2_5_2_streaming.txt`).

**Vì sao writer 1 xoá rồi ghi lại thay vì "chỉ thêm dòng mới"?** Vì mỗi lần nạp
artifact là nạp **một version hoàn chỉnh mới** (ví dụ `als_topn.json` của
`v1.0.0`), không phải nạp thêm — xoá sạch version cũ trước khi ghi đảm bảo chạy
lại script này 2 lần cho ra đúng 1 bộ dữ liệu, không có document rác từ lần chạy
trước còn sót lại.
