## 1. Kiểm chứng streaming nhận phim thêm sau (làm đầu tiên — design D-7)

- [x] 1.1 Bật lại container `spark` + chạy `streaming.pipeline`; khi pipeline đã chạy, chèn 1 phim thử `_id = 9000000` (genres `Crime|Drama`) vào `movies` bằng mongosh
- [x] 1.2 Gửi rating cho phim đó qua `POST /ratings` → xác nhận `GET /ratings/{eventId}` thành `applied` và quarantine không có `eventId` này; gửi thêm 1 event movieId lạ qua CLI producer → xác nhận vẫn vào quarantine với `unknown_movie_id`
- [x] 1.3 Nếu 1.2 thất bại: chuyển kiểm tra tồn tại phim của nhánh hợp lệ vào `serve_batch` (pymongo mỗi batch) theo cách dự phòng D-7, chạy lại 1.2 cho tới khi PASS — BỎ QUA: 1.2 PASS (pipeline nhận phim thêm sau), không cần sửa
- [x] 1.4 Xoá phim thử, ghi kết quả + kết luận vào `evidence/p2_demo_new_movie_streaming.txt`

## 2. Config & repository

- [x] 2.1 `configs/serving.yaml`: thêm `new_items` (`enabled: true`, `slots: 1`, `position: 3`, `window_days: 30`, `id_range_start: 9000000`) và `api.rating_poll_timeout_seconds: 60`; cập nhật `ServingConfig` + `load_serving_config`
- [x] 2.2 Bộ nạp config đọc `retrain_trigger.n_min_events` từ `configs/streaming.yaml` (một nguồn duy nhất, D-8)
- [x] 2.3 `ServingRepository` + `MongoServingRepository` + `FakeServingRepository`: `get_demo_movies(since)`, `create_demo_movie(title, genres, now)` (id kế tiếp trong dải, thử lại khi trùng khoá), `delete_demo_movie(movie_id)`, `get_model_registry()`, `get_retrain_progress()` (cùng truy vấn với `retrain_trigger.py`)

## 3. Nguồn gợi ý phim mới

- [x] 3.1 Module thuần `src/serving/new_items.py`: `genre_profile(seed_genres)`, `score_new_movies(profile, movies)` (xếp điểm ↓, `addedAt` ↓, `movieId` ↑), `place_new_items(final, new, slots, position, k)`
- [x] 3.2 Tích hợp vào `service.get_recommendations` cho tier few/enough (sau fill, trước enrich): lấy seed như nguồn content, loại phim user đã rate, gắn `source` chứa `new`; tier 0 và `enabled: false` giữ nguyên hành vi cũ
- [x] 3.3 Unit test: hồ sơ thể loại + chấm điểm; chèn đúng hạng và vẫn đủ `k`; phim không hợp thể loại không vào; phim đã rate bị loại; tier 0 không chèn; `enabled: false` cho kết quả y hệt trước; toàn bộ test cũ vẫn PASS

## 4. API routes

- [x] 4.1 `schemas.py`: `MovieIn {title, genres[]}`, `MovieCreated {movieId, title, genres}`, `SystemStatusOut` (activeVersion, versions[], retrainProgress {pending, nMin, watermark}, demo {ratingPollTimeoutSeconds})
- [x] 4.2 `POST /movies` (201/422/404) — validate title ≤200, genres ⊂ 19 thể loại MovieLens; `DELETE /movies/{movieId}` (204, 404 ngoài dải hoặc không tồn tại, không xoá rating)
- [x] 4.3 `GET /debug/system` (404 khi cờ tắt)
- [x] 4.4 Unit test: gating 404 cho cả 3 route; 422 thể loại sai/title rỗng; xoá phim MovieLens bị 404; id cấp trong dải ≥ 9,000,000; system status trả đúng version + gate checks + pending

## 5. Seed user cho case

- [x] 5.1 `scripts/seed_demo_users.py`: gửi rating qua `POST /ratings` với `eventId = uuid5(userId:movieId)`; mặc định user `700008` rate 296, 318, 858 (4.5 sao); tham số `--user-id` để tạo user mới khi user cũ đã "tiêu hao"
- [x] 5.2 Chạy 2 lần trên stack thật → xác nhận `interaction_count` = 3 và số `rating_events` của các `eventId` seed không đổi sau lần 2; ghi vào evidence

## 6. Trang `/demo`

- [x] 6.1 Dropdown "Case test" (1–9 + "có ALS" + "thiếu ALS") thay 3 nút preset, giữ ô nhập `userId`; danh mục case tĩnh chép từ bảng của nhóm (D-1)
- [x] 6.2 Chọn user theo D-2: case 1/7/9 sinh user 5xxxxx và kiểm tra `interaction_count == 0` (thử lại ≤5 lần); case 2/3/4/8 dùng user seed; "có ALS" = 1; "thiếu ALS" = 127249
- [x] 6.3 Thẻ case: 5 cột kỳ vọng (Điều gì xảy ra / Recommendation / Streaming / ALS Retrain / Chốt) đặt cạnh tier/strategy quan sát được + `interaction_count` hiện tại
- [x] 6.4 Case 3/4/9: form thêm phim (title + chọn thể loại), danh sách phim demo kèm nút xoá; phim có `source` chứa `new` được gắn nhãn "MỚI"
- [x] 6.5 Case 5/6: panel đọc `GET /debug/system` — bảng version (active/rejected + gate checks), thanh tiến độ pending/`n_min_events`, dòng "lịch chốt 1 tuần — chưa có scheduler"; không có nút kích hoạt
- [x] 6.6 Thời gian chờ poll lấy từ `demo.ratingPollTimeoutSeconds` (mặc định 60 nếu không gọi được)

## 7. Kiểm thử thật trên stack + trình duyệt

- [x] 7.1 Đi lần lượt từng case trên trình duyệt: 1, 7 (popularity), 8 (few_history), "có ALS", "thiếu ALS" (fallback tô màu), 2 (⭐ → applied → phim biến mất)
- [x] 7.2 Case 3: tạo phim Crime|Drama → xuất hiện hạng 3, nhãn MỚI cho user 700008; tạo phim Western → không xuất hiện
- [x] 7.3 Case 4: user 700008 rate phim demo → `applied`, không quarantine → phim biến mất khỏi gợi ý của user đó
- [x] 7.4 Case 9: user mới rate 1 phim Crime/Drama → `few_history` và phim demo xuất hiện
- [x] 7.5 Case 5/6: panel hiện `v1.0.0 active`, `v1.1.0 rejected` + gate checks; pending tăng đúng số rating vừa áp dụng
- [x] 7.6 Network log chỉ gọi API cùng origin; xoá hết phim demo sau khi test; ghi `evidence/p2_demo_cases.txt`

## 8. Tài liệu & bàn giao

- [x] 8.1 `docs/TESTING_GUIDE.md` mục 2b: kịch bản demo theo case (thứ tự gợi ý, bước seed, bước tạo/xoá phim, dọn dẹp trước khi nạp lại bootstrap)
- [x] 8.2 `docs/SERVING_ARCHITECTURE.md`: nguồn `new` + vị trí dành riêng trong sơ đồ luồng request (§2)
- [x] 8.3 `docs/DEPLOYMENT_DESIGN.md`: phim demo chỉ nằm trong MongoDB, không vào `curated_movies` (D-10); route ghi catalog tắt ở production
- [x] 8.4 Soạn ghi chú bàn giao cho Person 1: (a) popularity WR/Bayesian — định nghĩa + bảng so sánh `m` đã tính; (b) `movieId` ≥ 9,000,000 có thể xuất hiện trong `curated_ratings` từ demo
