## Why

Quyên (Person 1) đã review chéo PR #1 trước khi merge: 10 finding, 4 cái gắn nhãn blocker (comment trên PR #1 và `docs/REVIEW_person2_branch.md` trong PR #2). Mình đối chiếu từng finding với code thật: số dòng đều khớp, và phần lớn là lỗi ở **đường lỗi** (crash, restart, retry) nên không nổ ở happy path, đúng như review nói. Kết quả đối chiếu:

- **Đúng và nên sửa trước merge:** B1 (watermark handoff), B3 (guard `batchId` so với checkpoint), phần phía gate của B2 (`promotion_gate` đọc `curated_ratings` không dedup).
- **Đúng nhưng hạ mức:** B4 (`bootstrap_registry` ghi đè pointer) hiện bị chặn do ngẫu nhiên bởi `EXPECTED` đếm đúng số document; trên DB đang chạy `popular_movies` có 2 (kỳ vọng 1), `user_rated` 32,000,245 (kỳ vọng 32,000,204), `user_history` 200,960 (kỳ vọng 200,948), nên G4 fail và `return 1` trước khi ghi pointer. Vấn đề thật là README ghi "safe to rerun" sai và sự bảo vệ không chủ đích. B2 phía parquet đã được `design.md` D-10 ghi nhận (append có thể chạy hai lần, xử lý bằng latest-wins khi đọc, D4 chờ Quyên xác nhận) nên không phải blocker, chỉ cần khép vòng ở gate.
- **Review có hai chỗ chưa chính xác** cần biết để sửa đúng: `maxEventTimestamp` (dòng 96) có được dùng (manifest, checksum) và là thời điểm của rating chứ không phải `ingestedAt`, nên không được dùng làm watermark; B3 không "skip vĩnh viễn" mà skip tới khi `batchId` vượt `lastBatchId`, và log in "already committed … skipping".

Quyên bắt đầu B6/B8 trên `orchestration/` và `curated_ratings`, nên các lỗi này cần xong trước khi phần của Quyên dựa vào. M8 là 03/10/2026, nên scope giữ nhỏ, mỗi sửa đổi có cách kiểm chứng riêng.

## What Changes

**Sửa trước khi merge PR #1 (fault-path, không đổi hành vi happy path)**
- **B1 — cửa sổ handoff theo event đã commit.** `retrain_trigger` chỉ xuất các event có `ingestedAt` trong `(watermark, committedUpTo]`, với `committedUpTo` là `lastRunAt` của batch đã commit gần nhất trong `pipeline_state.ratings_stream`; watermark mới bằng `committedUpTo`. Event của batch đang ghi dở không lọt vào cửa sổ, và không có event nào rơi giữa lúc truy vấn và lúc ghi watermark.
- **B3 — guard `batchId` gắn với checkpoint đã ghi ra nó.** `pipeline_state.ratings_stream` lưu thêm `streamId` (id trong file `metadata` của checkpoint Q2). Guard chỉ bỏ qua batch khi `streamId` trùng; khi khác hoặc không đọc được, in cảnh báo rõ ràng, đặt lại `lastBatchId` và dựa vào ledger (đã đủ để replay an toàn với Mongo).
- **B2 — khép vòng ở phía gate.** `promotion_gate` dedup holdout theo `(userId, movieId)`, giữ dòng có `timestamp` lớn nhất, trước khi tính RMSE. Ghi rõ vào D-10 là append parquet vẫn at-least-once và hỏi Quyên xác nhận D4 cho phía retrain.
- **B4 — bootstrap không ghi đè pointer đang hoạt động.** `bootstrap_registry` từ chối ghi `serving_meta.active` khi đã có pointer khác `--version`, chỉ dẫn sang `promotion_gate` / `manage_versions`. README bỏ chữ "idempotent — safe to rerun", mô tả đúng bước này là nạp lần đầu và sẽ fail G4 khi đã có rating mới.
- **M1 — gate fail-closed khi thiếu `cut_test`.** Thiếu ở cả hai model card thì G1–G3 FAIL với lý do rõ ràng, không còn tính RMSE trên toàn bộ dữ liệu.
- **M2 — hợp đồng timeout của `POST /ratings`.** 503 do timeout nghĩa là *kết quả chưa biết*; thông báo nói rõ phải retry với cùng `eventId`. Trang `/app` giữ lại `eventId` cho lần thử lại cùng một đánh giá sau khi lỗi.

**Dọn nhỏ (rủi ro thấp, kèm test)**
- `place_new_items`: điểm của phim mới được chèn luôn không tăng dần, kể cả khi `slots` > 1.
- `pipeline.py`: schema `kafkaTimestamp` khai đúng kiểu timestamp thay vì string.
- `repository.get_user_history`: dùng chung một hàm đổi datetime sang epoch, coi datetime không có múi giờ là UTC (giống `retrain_trigger`).
- `serve_batch`: dùng lại một `MongoClient` cho cả tiến trình thay vì tạo mới mỗi micro-batch.

**Không đổi:** thứ tự `serve_batch` (parquet → `user_rated` → `user_history` → ledger → commit), schema `curated_ratings` (đóng băng ở CONTRACTS §2.1, không thêm cột), hành vi API ở happy path, fusion/router.

**Ngoài phạm vi (trả lời Quyên ở PR #2, không sửa ở đây):** nhãn `modelVersion: "v1.0.0"` giữ nguyên dù nội dung `popular_movies.json` đổi; `evidence/b3_1_split_baseline.txt` bị ghi đè; `m=1000` được chọn theo kết quả mong muốn và chưa có bảng nhạy cảm; popularity chỉ tính trên tập train và chỉ có 10 phim. Câu hỏi D3 (holdout `timestamp ≥ cut_test` tự lớn lên khi streaming ghi rating mới, còn delta lại nằm đúng trong cửa sổ đó) hỏi Quyên khi chốt B6.

## Capabilities

### New Capabilities
<!-- Không có capability mới. -->

### Modified Capabilities
<!-- openspec/specs/ đang trống (4 change trước chưa archive) nên các delta dưới đây viết dạng ADDED trong thư mục cùng tên capability. Archive change này SAU `person2-serving-streaming-integration` và `add-demo-web-client`/`demo-use-case-scenarios`. -->
- `rating-stream-ingestion`: guard `batchId` gắn với danh tính checkpoint (B3).
- `model-refresh-orchestration`: cửa sổ handoff theo event đã commit (B1); holdout của gate được dedup (B2); gate fail-closed khi thiếu `cut_test` (M1).
- `serving-store`: bootstrap không ghi đè pointer đang hoạt động (B4).
- `rating-ingestion-api`: 503 do timeout là kết quả chưa biết, client dùng lại `eventId` để retry (M2).
- `new-movie-cold-start`: điểm của các phim mới chèn vào không tăng dần.

## Impact

- **Code:** `src/orchestration/retrain_trigger.py`, `src/orchestration/promotion_gate.py`, `src/streaming/pipeline.py`, `src/loaders/bootstrap_registry.py`, `src/api/main.py`, `src/api/static/app.html`, `src/serving/new_items.py`, `src/serving/repository.py` (+ `tests/unit/fakes.py`).
- **Dữ liệu:** `pipeline_state.ratings_stream` có thêm trường `streamId` (additive; bản ghi cũ không có trường này vẫn đọc được). Không đổi schema collection nào khác, không đổi `curated_ratings`.
- **Docs:** `README.md` (bước 2), `design.md` của `person2-serving-streaming-integration` D-10 (ghi nhận at-least-once và dedup ở gate), `docs/TESTING_GUIDE.md` (mục streaming, thêm ca restart mất checkpoint), cập nhật số test trong README.
- **Quan hệ với PR:** các sửa đổi nằm trên nhánh `feat/person2-serving-streaming-integration` (PR #1); không đụng file nào của PR #2.
- **Rủi ro chính:** B3 và B1 đụng vào đường chạy của streaming đang hoạt động; kiểm bằng `docker compose` thật (mất checkpoint giả lập, handoff giữa lúc ghi), không chỉ unit test.
- **Thời gian:** khoảng nửa ngày; B1 + B3 chiếm phần lớn vì cần kiểm trên stack thật.
