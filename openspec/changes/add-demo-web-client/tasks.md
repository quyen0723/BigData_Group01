## 1. Giai đoạn A+ — đường ghi rating qua HTTP (~2h; xong là Swagger `/docs` demo được cả vòng lặp)

- [x] 1.1 `configs/serving.yaml`: thêm `api.demo_enabled` (mặc định `false`), `api.kafka_bootstrap_servers_env`, `api.ratings_topic`, `api.produce_timeout_seconds` (10)
- [x] 1.2 `docker/docker-compose.yml`: service `api` thêm env `KAFKA_BOOTSTRAP_SERVERS=kafka:9092` — **không** thêm `depends_on: kafka` cứng (design D-7)
- [x] 1.3 `src/api/schemas.py`: `RatingIn {userId, movieId, rating, eventId?}`, `RatingAccepted {eventId, status:"accepted"}`, `RatingStatus {eventId, status, batchId?, ingestedAt?}`
- [x] 1.4 `src/api/main.py`: dependency `get_producer()` tạo lười 1 producer/process, tái dùng `streaming.producer.make_producer` (acks=all, idempotence)
- [x] 1.5 `POST /ratings`: validate (userId>0, rating ∈ `VALID_RATINGS`, movieId tồn tại qua `movies._id`, eventId ≤64 ký tự) → gán timestamp server → sinh eventId nếu thiếu → produce + `flush(timeout)` + kiểm delivery → 202 / 422 / 503
- [x] 1.6 `GET /ratings/{eventId}`: tra `rating_events` → `applied` (+batchId, ingestedAt) hoặc `pending`
- [x] 1.7 Unit test (`tests/unit/test_ratings_api.py`) với producer giả + FakeServingRepository: 202 happy path, 422 ×4 luật (không gọi producer), 503 khi producer báo lỗi, eventId client được giữ nguyên, status pending/applied
- [x] 1.8 Kiểm thử thật qua Swagger trên stack: POST → 202 → GET status `pending` → `applied`; tắt Kafka → POST 503 nhưng GET /recommendations vẫn 200 → ghi `evidence/p2_demo_rating_api.txt`

## 2. Giai đoạn B — trang `/demo` (~nửa ngày)

- [x] 2.1 `GET /debug/users/{userId}` (chỉ khi `demo_enabled`, ngược lại 404): user_history + pipeline_state + serving_meta; user chưa có history → count 0, list rỗng
- [x] 2.2 `GET /demo` → `FileResponse(src/api/static/demo.html)` (chỉ khi `demo_enabled`, ngược lại 404)
- [x] 2.3 `src/api/static/demo.html` — khung bố cục chia đôi, CSS inline, không tài nguyên ngoài; nhãn "Demo web client — demo-only"
- [x] 2.4 Chọn user: ô nhập + 3 preset (user mới ngẫu nhiên `5xxxxx`, user 1, user 127249); thẻ phim (title, genres, rank, source, màu theo thể loại chính)
- [x] 2.5 Panel "bên trong hệ thống": tier/strategy/fallbackReason/modelVersion/latency từ response + interaction_count/last batch từ `/debug`; highlight fallback
- [x] 2.6 Vòng lặp ⭐: `crypto.randomUUID()` → POST → log 202 → poll status 1s/30s → applied: reload + highlight thay đổi (tier đổi, phim biến mất) → timeout: gợi ý "streaming có đang chạy?"
- [x] 2.7 Unit test: `/debug` và `/demo` trả 404 khi cờ tắt, 200 khi bật; `/debug` user rỗng
- [x] 2.8 Kiểm thử thật trên trình duyệt (in-app browser) theo 5 bước kịch bản demo; kiểm network log chỉ gọi API origin; thử ngắt mạng → trang vẫn chạy → ghi `evidence/p2_demo_ui.txt` + ảnh chụp màn hình

## 3. Tài liệu & phương án dự phòng

- [x] 3.1 `docs/TESTING_GUIDE.md`: thêm mục "Demo bằng giao diện" (bật cờ, mở `/demo`, 5 bước kịch bản, bước terminal tắt/bật streaming)
- [x] 3.2 `docs/SERVING_ARCHITECTURE.md`: hộp USER APP → "Demo web client (Implemented, demo-only)" + route `POST /ratings` trên sơ đồ tổng thể (§0/§1)
- [x] 3.3 `docs/DEPLOYMENT_DESIGN.md`: trade-off "API vừa đọc vừa ghi" → hướng tách ingestion service; `/debug` + `/demo` tắt ở production (§Security)
- [ ] 3.4 Quay video toàn bộ kịch bản demo (phương án dự phòng khi Docker Desktop sập giữa buổi thuyết trình)
