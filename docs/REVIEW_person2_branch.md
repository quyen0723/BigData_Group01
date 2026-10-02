# Code Review — nhánh `feat/person2-serving-streaming-integration` của Person 2

> **Reviewed:** 2026-10-02 — Person 1 (Quyên) side, cross-review trước khi branch merge.
> **Scope:** `main..origin/feat/person2-serving-streaming-integration` — 4 commits (`0ceba11`→`421d088`), ~11K dòng, 113 files.
> **Phương pháp:** `/code-review` (high) fan-out 8 góc nhìn + **verify thủ công line-by-line** trên worktree
> `.claude/worktrees/person2-review`. Mọi finding dưới đây đã đối chiếu với code thật; 8/10 chính xác
> hoàn toàn, 2/10 đúng nhưng có cải bổ sung (ghi rõ ở mỗi mục).
> **Kết quả: 0 finding sai.**

| # | File | Mức | Trạng thái verify |
|---|------|-----|-------------------|
| 1 | `src/orchestration/retrain_trigger.py:117` | 🔴 High | ✅ Chính xác 100% |
| 2 | `src/streaming/pipeline.py:191` | 🔴 High | ✅ Chính xác 100% |
| 4 | `src/streaming/pipeline.py:155` | 🔴 High | ✅ Chính xác 100% |
| 7 | `src/loaders/bootstrap_registry.py:117` | 🔴 High | ✅ Chính xác 100% |
| 3 | `src/orchestration/promotion_gate.py:112` | 🟠 Medium | ⚠️ Đúng code path, trigger khó hơn mô tả |
| 6 | `src/api/main.py:207` | 🟠 Medium | ⚠️ Đúng 50/50 tùy client |
| 8 | `src/streaming/pipeline.py:94` | 🟡 Low (latent) | ✅ Chính xác là latent |
| 5 | `src/serving/repository.py:80` | 🟡 Low | ✅ Chính xác |
| 9 | `src/serving/new_items.py:77` | 🟡 Low | ✅ Chính xác (vô hại ở slots=1) |
| 10 | `src/streaming/pipeline.py:150` | 🟡 Low (perf) | ✅ Chính xác |

---

## 🔴 High

### 1. Watermark lỗ đen — `retrain_trigger.py:117` ✅
Line 51 query `pending = find({ingestedAt: {$gt: since}})`; line 97 chụp
`now = datetime.now(utc)`; line 117 ghi `watermark = now`.

Mọi event được ledger-apply **sau** line 51 và **trước** line 97/117 có `ingestedAt ≤ now`
→ không thuộc package này, và lần sau cũng bị loại. Khe hở chứa Spark parquet write
(lines 72-88) nên có thể mấy chục giây. Bonus: line 96 đã tính `maxEventTimestamp` nhưng
không dùng — nên watermark = **max `ingestedAt` của `pending`** thay vì `now`.

### 2. `serve_batch` không idempotent với `curated_ratings` — `pipeline.py:191` ✅
`curated_df.write.mode("append").parquet(curated_ratings_path)` (line 191) chạy **trước**
ledger insert (line 250 — idempotency marker). Crash giữa hai bước (OOM/kill) → Spark
checkpoint giữ batch là chưa-commit → re-run batch: `eventId` chưa có trong ledger →
`new_rows` non-empty lần 2 → **append trùng (userId, movieId, rating)** vào
`curated_ratings` (dữ liệu train của Person 1).

`user_rated` upsert + `user_history` recompute đều idempotent; chỉ parquet append là
không — nhưng đó chính là bảng train. Comment line 241-242 cho biết chủ đích
"in ledger always means already applied" — nhưng parquet nằm ngoài vùng bảo vệ.

### 4. Guard `batchId` so checkpoint transient với Mongo durable — `pipeline.py:155` ✅
Lines 153-157: skip khi `batch_id <= last_batch_id`. `batch_id` của Spark là counter
**per-checkpoint**; mất checkpoint dir (cleanup disk, remount bundle) trong khi Mongo giữ
`lastBatchId=43` → query restart từ batch 0 → **mọi batch bị skip vĩnh viễn**, vẫn ghi
"committed" (line 256). Rating đứng ở "pending" mãi, log nhìn vẫn healthy.

### 7. `bootstrap_registry` ghi đè vô điều kiện active pointer — `bootstrap_registry.py:117` ✅
Lines 117-131: `replace_one` serving_meta active với `--version`, `previousVersion: None`,
không qua gate RMSE nào. README.md:71 ghi đúng chữ:
`# 2. Load MongoDB serving store (idempotent — safe to rerun)` → mâu thuẫn behavior:
rerun sau khi `promotion_gate` promote v1.1.0 = **rollback model live không gate**.
Hardcoded EXPECTED counts cũng break khi streaming đã apply events.

---

## 🟠 Medium

### 3. Gate fail-open khi thiếu `cut_test` — `promotion_gate.py:112` ⚠️ *đúng code, nuance trigger*
**Code path có thật:** line 96 `cut_test = candidate...get("cut_test") or active...get(...)`;
nếu **cả hai** card thiếu → `cut_test is None` → line 111 bỏ filter → line 110 đọc toàn bộ
`curated_ratings` → G1-G3 tính RMSE trên **train data**, không log/cảnh báo gì.

**Nuance:** trigger khó hơn báo cáo ban đầu — `artifacts/model_card.json` thật của M1/M2
**có** `split.cut_test: 1573258563.0`, và `stage_candidate.py` nhận card optional.
Chỉ xảy ra với card hỏng/thiếu trường → không phải flow bình thường. Đề nghị:
log **FAIL hoặc WARN rõ ràng** khi `cut_test is None` thay vì đi tiếp im lặng.

### 6. 503 không đảm bảo non-delivery — `api/main.py:207` ⚠️ *đúng 50/50 tùy client*
Line 200 `remaining = producer.flush(timeout)`; `remaining > 0` → 503 "delivery timed out".
Nhưng message đã vào queue librdkafka ở line 194 và thread background có thể deliver sau.
Đối chứng thêm: `main.py:173-175` — client gửi `eventId` riêng thì retry giữ nguyên eventId,
ledger dedup chặn double-apply; **nếu client để server tự sinh `uuid4`** (line 175) thì mỗi
retry là eventId mới + message cũ vẫn deliver → double-apply thật (giá trị rating sau cùng
thắng). Cần quyết định contract: client bắt buộc supply eventId, hoặc dùng
`eventId` idempotency-key và nói rõ trong spec.

---

## 🟡 Low

### 8. Schema mis-declare `kafkaTimestamp` — `pipeline.py:94` (latent) ✅
Q1 ghi `"timestamp as kafkaTimestamp"` từ Kafka source (TimestampType) → parquet INT96;
`build_parsed_stream` khai StringType. Hện ẩn vì mọi select không đọc 4 cột kafka*;
chạm vào là Spark throw `cannot be converted... Expected string, Found INT96`. Sửa
khai báo đúng kiểu (TimestampType/Int) để tránh bẫy cho thay đổi tương lai.

### 5. Naive datetime `.timestamp()` — `repository.py:80` ✅
pymongo trả naive datetime → `.timestamp()` hiểu theo local time → `lastUpdated` sai
epoch trên host non-UTC (container UTC không bị). Trong cùng codebase
`retrain_trigger.py:48-49` làm đúng (`replace(tzinfo=utc)`) — chuẩn hóa 1 helper `to_epoch`.

### 9. Scores không descending khi slots > 1 — `new_items.py:77` ✅
`final=[a,b,c], slots=2, position=2` → `[a, b, c, b, c]`: rank4 (b) < rank3 (c) — vi phạm
invariant chính module tự ghi (dòng 63-64). Vô hại hiện tại (slots=1) nhưng sai khi tăng.

### 10. MongoClient mới mỗi micro-batch — `pipeline.py:150` (perf) ✅
Line 150 nằm trong `serve_batch` — kể cả batch rỗng mỗi 5s → ~17K clients/ngày, mỗi cái
discovery/handshake. Reuse process-level client như `promotion_gate`/`retrain_trigger`.

---

## Ảnh hưởng tới Person 1 (B6/B8)

- **#2** đụng `curated_ratings` — dữ liệu train (B6.1 retrain nằm ngay phía sau).
- **#1, #3** nằm trong `orchestration/` — chính là contract B6.1/B6.2 của Person 1 sẽ dùng.
- **Khuyến nghị:** các finding #1/#2/#4/#7 fix **trước khi merge** vào `main`; B6/B8 chỉ
  bắt đầu trên nhánh đã có fix (đặc biệt #2 vì retrain đọc chính curated_ratings).