## 1. Chuẩn bị và mốc so sánh

- [x] 1.1 Chạy toàn bộ unit test hiện tại (`.venv-serving/Scripts/python -m pytest tests/ -q`), ghi số test và kết quả làm mốc (kỳ vọng 124 pass); `git status` xác nhận đang ở nhánh `feat/person2-serving-streaming-integration`
- [x] 1.2 Tạo `evidence/p2_review_fixes.txt` với mục lục theo finding (B1, B2, B3, B4, M1, M2, nhỏ), mỗi mục có dòng "trước" và "sau"; các task dưới đây ghi kết quả vào đây
- [x] 1.3 Chụp trạng thái cần khôi phục sau các thử nghiệm trên stack thật: `pipeline_state` (`ratings_stream`, `retrain_handoff`, `demo_movie_seq`), số document `rating_events`; ghi vào evidence để so sánh khi dọn dẹp

## 2. B1 — cửa sổ handoff theo event đã commit (D-1)

- [x] 2.1 Module thuần `src/orchestration/handoff_window.py` (không import pyspark): lấy `committedUpTo` từ document `ratings_stream` (chuẩn hóa múi giờ UTC), dựng điều kiện `ingestedAt` trong `(since, committedUpTo]`, trả `None` khi không có `lastRunAt`
- [x] 2.2 `retrain_trigger.py`: đọc `committedUpTo` một lần ở đầu; lọc `pending` theo cửa sổ; `watermark` và `windowEnd` của manifest bằng `committedUpTo`; `createdAt` vẫn là `now`; không có `committedUpTo` thì in "nothing committed" và thoát 0 không tạo package
- [x] 2.3 Unit test (`tests/unit/test_handoff_window.py`): batch có `ingestedAt` sau `lastRunAt` bị loại; batch nửa vời bị loại; event `ingestedAt == lastRunAt` được lấy; hai lần handoff liên tiếp cho hợp = mọi event đúng một lần; không có `ratings_stream` → `None`; datetime không múi giờ coi là UTC
- [x] 2.4 Kiểm trên stack thật bằng event tổng hợp có prefix `review-fix-`: (a) đặt `lastRunAt = T`, chèn ledger `ingestedAt = T - 1s` và `T + 5s`, chạy `retrain_trigger --force` → package chỉ có event đầu, watermark = T; (b) đẩy `lastRunAt = T + 10s`, chạy lại → package chỉ có event còn lại. Ghi kết quả vào evidence, rồi xoá event tổng hợp, khôi phục `pipeline_state` theo task 1.3 và xoá thư mục handoff thử nghiệm

## 3. B3 — guard `batchId` gắn với checkpoint (D-2)

- [x] 3.1 Tái hiện lỗi trên code hiện tại (trước khi sửa): dừng `streaming`, đổi tên thư mục checkpoint `valid` thành `valid.bak`, khởi động lại, gửi một rating của user mới qua `/ratings`; ghi log `serve_batch[...]: already committed … skipping` và trạng thái `pending` vào evidence ("trước")
- [x] 3.2 Module thuần `src/streaming/batch_guard.py`: `decide_batch_action(state, batch_id, stream_id)` trả `process`/`skip`/`reset` kèm lý do; `read_stream_id(checkpoint_dir)` đọc `metadata`, trả `None` khi thiếu hoặc hỏng
- [x] 3.3 Unit test (`tests/unit/test_batch_guard.py`): state rỗng; cùng stream và `batch_id <= last` → skip; cùng stream và `batch_id > last` → process; khác stream → reset; `stream_id` không đọc được → process; state cũ không có `streamId` → cùng stream; `read_stream_id` với file hợp lệ, thiếu, JSON hỏng
- [x] 3.4 `pipeline.py`: `serve_batch` dùng `decide_batch_action`; `reset` in cảnh báo "checkpoint changed" và coi `lastBatchId` là -1; `process` do không đọc được id in cảnh báo một lần; bước 7 ghi `streamId` cùng `lastBatchId`. Giữ nguyên dòng log skip khi cùng stream. `collect()` batch đứng **trước** quyết định skip để state store dedup luôn đi cùng offset (phát hiện ở 3.1: skip mà không đọc batch làm hỏng checkpoint)
- [x] 3.5 Chạy lại kịch bản của 3.1 trên code mới: log có cảnh báo "checkpoint changed", rating mới thành `applied`, `lastBatchId` đặt lại; số dòng `rating_events` và `user_rated` của các event cũ không đổi (replay không nhân đôi). Ghi vào evidence ("sau"), xoá `valid.bak` và event thử nghiệm
- [x] 3.6 Kiểm khôi phục bình thường: `docker compose restart streaming` (checkpoint còn nguyên) → batch có `batchId <= lastBatchId` vẫn bị skip với log cũ
- [x] 3.7 Kiểm skip không làm hỏng state: đặt `lastBatchId` rất lớn cùng `streamId` hiện tại, gửi hai rating liên tiếp → cả hai bị skip có log, query vẫn sống và không có `FileNotFoundException` ở file state; khôi phục `lastBatchId` rồi gửi rating thứ ba → `applied`

## 4. B2 và M1 — promotion gate (D-3, D-5)

- [x] 4.1 Module thuần `src/orchestration/gate_holdout.py` (không import pyspark): `resolve_cut_test(candidate_card, active_card)` trả giá trị hoặc `None`; không dùng toán tử `or` với giá trị 0
- [x] 4.2 `promotion_gate.py` (M1): `cut_test is None` → G1–G3 FAIL với lý do `no split.cut_test in either model card; refusing to evaluate on the full curated ratings`, không đọc parquet và không nạp model; G4–G7 vẫn chạy; báo cáo vẫn ghi vào `model_registry` và file evidence; dùng lại nhánh `rmse_error`
- [x] 4.3 `promotion_gate.py` (B2): sau khi lọc `timestamp >= cut_test`, gộp theo `(userId, movieId)` bằng `max_by("rating", "timestamp")` trước khi tính RMSE của cả active và candidate
- [x] 4.4 Unit test (`tests/unit/test_gate_holdout.py`): cả hai card thiếu → `None`; chỉ active có → dùng giá trị đó; candidate có → ưu tiên candidate; giá trị 0 không bị coi là thiếu
- [x] 4.5 Kiểm trên Spark trong container với parquet tổng hợp (không đụng `curated_ratings` thật): holdout có một dòng bị lặp hai lần cho cùng RMSE như khi chỉ có một dòng; holdout không có cặp lặp cho RMSE y hệt bản không gộp. Đo thời gian phép gộp trên holdout thật (≈4.8M dòng, chỉ đọc) và ghi vào evidence
- [x] 4.6 Chạy `promotion_gate` với hai model card thiếu `cut_test` (bản sao tạm của candidate đã stage): G1–G3 FAIL đúng lý do, candidate không được promote, `serving_meta.active` không đổi

## 5. B4 — bootstrap và README (D-4)

- [x] 5.1 `bootstrap_registry.py`: sau khi kết nối, đọc `serving_meta.active`; nếu có và khác `--version` thì in lý do, nhắc `promotion_gate`/`manage_versions`, thoát mã 2 trước mọi kiểm tra và ghi; cùng version hoặc chưa có pointer thì chạy như cũ
- [x] 5.2 Kiểm trên Mongo thật: `bootstrap_registry --version v9.9.9` khi active là `v1.0.0` → mã thoát 2, `serving_meta` và `model_registry` không đổi (so sánh trước/sau); ghi vào evidence
- [x] 5.3 `README.md` bước 2: bỏ "idempotent — safe to rerun", ghi đây là bước nạp lần đầu, sẽ fail kiểm đếm G4 khi đã có rating mới hoặc đã nạp version thứ hai, và cách nạp lại khi cần (xoá `serving_meta` sau khi xoá dữ liệu). Cập nhật số test ở mục Tests theo kết quả thật

## 6. M2 — hợp đồng timeout của `POST /ratings` (D-6)

- [x] 6.1 `src/api/main.py`: thông báo 503 khi `flush()` quá hạn thành `kafka delivery timed out; the rating may still be delivered, retry with the same eventId`; các nhánh 503 khác giữ nguyên
- [x] 6.2 Unit test trong `tests/unit/test_ratings_api.py`: thông báo 503 timeout chứa "same eventId"; gửi hai lần cùng `eventId` sau timeout vẫn trả 202 với `eventId` đó
- [x] 6.3 `src/api/static/app.html`: giữ `eventId` theo khóa `userId:movieId:số sao` cho lần thử lại sau mọi kết quả khác 202 hoặc 422; xoá khi nhận 202 hoặc 422; đăng xuất hoặc đổi tài khoản không để lại id của tài khoản khác
- [x] 6.4 Kiểm trên trình duyệt: ghi đè `fetch` để lần POST đầu trả 503, bấm sao lần nữa → hai request mang cùng `eventId`; sau 202 và bấm sao khác cho cùng phim → `eventId` mới. Ghi vào evidence
- [x] 6.5 `docs/TESTING_GUIDE.md`: ghi hợp đồng "503 = kết quả chưa biết, retry cùng `eventId`" ở mục `POST /ratings`

## 7. Dọn nhỏ (D-7)

- [x] 7.1 `new_items.place_new_items`: mọi phim chèn nhận điểm của phần tử đầu tiên bị đẩy xuống (hoặc phần tử cuối khi chèn cuối danh sách); thêm test trong `test_new_items.py`: `[0.9,0.8,0.7]`, 2 slot, vị trí 2 → điểm không tăng; chèn cuối; `slots=1` cho kết quả như trước
- [x] 7.2 `pipeline.py` `build_parsed_stream`: khai `kafkaTimestamp` là `TimestampType`; chạy lại streaming và xác nhận một rating đi hết đường tới `applied`
- [x] 7.3 `src/serving/timeutil.py`: `to_epoch(dt)` thuần, datetime không múi giờ coi là UTC; dùng ở `repository.get_user_history` và `retrain_trigger`; test với datetime có và không có múi giờ (kể cả khi đặt `TZ` khác UTC trong test)
- [x] 7.4 `serve_batch`: tạo `MongoClient` một lần trong closure (lazy), dùng lại cho mọi batch, bỏ `close()` mỗi batch; xác nhận bằng log hoặc `serverStatus().connections` rằng số kết nối không tăng sau nhiều batch rỗng

## 8. Tài liệu, evidence và đóng việc

- [x] 8.1 `openspec/changes/person2-serving-streaming-integration/design.md` D-10: thêm đoạn ghi nhận append parquet vẫn at-least-once và ba nơi trung hoà (`delta_ratings` lấy từ ledger, gate dedup, retrain theo D4); sửa bước 1 cho khớp guard theo checkpoint
- [x] 8.2 `docs/TESTING_GUIDE.md` mục streaming: thêm ca "mất checkpoint" (các bước của 3.1/3.5) và ca "handoff giữa lúc ghi" (2.4) ngắn gọn, kèm kết quả kỳ vọng
- [x] 8.3 Chạy toàn bộ unit test: số test = mốc 1.1 cộng test mới, 0 fail; không có `test.skip`/`.only`/stub rỗng (`grep` các file thay đổi)
- [x] 8.4 Hoàn thiện `evidence/p2_review_fixes.txt`: bảng 10 finding với kết luận (đúng/đúng-hạ-mức), cách sửa, bằng chứng trước/sau; ghi rõ cái chưa kiểm được (không tái hiện crash thật giữa append parquet và ledger)
- [x] 8.5 Soạn bản trả lời cho Quyên trên PR #1: đồng ý B1/B3/B2-gate/M1/M2, giải thích hạ mức B4 và B2-parquet kèm bằng chứng, nêu hai chỗ review chưa chính xác (`maxEventTimestamp`, log "committed"), hỏi D3/D4; kèm các điểm của PR #2 (nhãn `modelVersion`, evidence bị ghi đè, `m=1000` chưa có bảng nhạy cảm, top-10). Chỉ soạn nháp vào `docs/`; không đăng lên GitHub khi chưa được duyệt
- [x] 8.6 `openspec validate address-person1-review-findings --strict` pass; cập nhật checkbox; commit và push lên PR #1 chỉ khi người dùng yêu cầu
