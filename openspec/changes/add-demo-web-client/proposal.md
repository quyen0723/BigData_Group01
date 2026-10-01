## Why

Sơ đồ kiến trúc bắt đầu và kết thúc bằng hộp **"USER APP"**: user gửi request lấy gợi ý, và user gửi rating. Trong phần đã build (change `person2-serving-streaming-integration`), hộp này chưa tồn tại thật:

- Phía request đang do `curl`/Swagger UI đóng vai.
- Phía rating đang do CLI `streaming.producer` chạy trong container đóng vai. `docs/ARCH.txt` cho phép dùng "simulator trong demo".

Hệ quả cho buổi demo Session 10:

- Không có cách nào để một người **bấm trên trình duyệt** mà gửi được rating. API chỉ có 2 route GET, còn trình duyệt không thể ghi thẳng vào Kafka.
- Nếu chỉ gõ lệnh terminal thì các cơ chế đã verify (đổi tier, fresh-history exclusion, idempotency, eventual consistency) khó thấy và khó thuyết phục giám khảo.

Rubric Presentation (10%) yêu cầu "presentation/demo is clear". Change này lấp đúng hộp "USER APP" bằng một client demo tối thiểu. Toàn bộ luồng phía sau (Kafka → Structured Streaming → Mongo/Parquet) giữ nguyên.

## What Changes

**Giai đoạn A+ — đường ghi rating qua HTTP.** Swagger UI dùng được cho cả vòng lặp ngay sau giai đoạn này.
- `POST /ratings`:
  - Nhận `{userId, movieId, rating, eventId?}` và validate định dạng (trả 422 ngay nếu sai).
  - Sinh `eventId` nếu client không gửi.
  - Produce vào Kafka `ratings.v1` với key là `userId`.
  - Trả **202 Accepted** kèm `eventId`, nghĩa là đã nhận vào hàng đợi, chưa áp dụng.
- `GET /ratings/{eventId}`: tra sổ `rating_events` và trả `{applied: true|false}`. Route này làm cho tính bất đồng bộ của pipeline nhìn thấy được.
- Service `api` trong Docker Compose được nối tới Kafka: thêm `depends_on: kafka` và biến `KAFKA_BOOTSTRAP_SERVERS`.

**Giai đoạn B — trang demo.**
- `GET /demo` trả một file HTML tĩnh do chính FastAPI phục vụ. Không thêm container, không cần build tooling, không cần CORS.
- Bố cục chia đôi:
  - Bên trái là "user thấy gì": thẻ phim gợi ý, ⭐ để rate.
  - Bên phải là "bên trong hệ thống": `tier`, `strategy`, `fallbackReason`, `modelVersion`, latency, `interaction_count`, batch streaming gần nhất và nhật ký sự kiện.
- `GET /debug/users/{userId}` trả state cho panel bên phải. Route chỉ bật khi `api.demo_enabled=true` (**demo-only**).

**Không đổi:** streaming pipeline, validation phía streaming, dedup, Mongo schema, router/fusion/exclusion, promotion gate.

**Phạm vi:** client này là **demo-only**. Không phải tính năng sản phẩm, vì PRD §3.2 non-goal: *"Xây dựng Netflix clone ở production scale"*. Sơ đồ kiến trúc sẽ ghi hộp USER APP là "Demo web client (Implemented, demo scope)".

## Capabilities

### New Capabilities
- `rating-ingestion-api`: đường ghi rating qua HTTP.
  - `POST /ratings` gồm validate, sinh `eventId` và produce Kafka, trả 202.
  - `GET /ratings/{eventId}` tra trạng thái đã áp dụng hay chưa.
  - Quan hệ với validation phía streaming (defense-in-depth).
- `demo-web-client`:
  - Trang `/demo`: kịch bản tương tác (chọn user, xem gợi ý, rate, chờ áp dụng, tải lại) và panel "bên trong hệ thống".
  - `GET /debug/users/{userId}` có cờ bật/tắt bằng config.

### Modified Capabilities
<!-- Không có spec nào trong openspec/specs/ (change serving chưa archive) — không có capability bị sửa. -->

## Impact

- **Code:**
  - `src/api/main.py` thêm các route mới.
  - `src/api/schemas.py` thêm model request/response.
  - `src/api/static/demo.html` là file mới.
  - Tái dùng `streaming/producer.py::make_producer` và `streaming/events.py` (tập `VALID_RATINGS`).
- **Config:**
  - `configs/serving.yaml` thêm `api.demo_enabled` và `kafka` cho phía API.
  - `docker/docker-compose.yml`: service `api` được thêm `depends_on: kafka` và `KAFKA_BOOTSTRAP_SERVERS`.
- **Dependencies:** không thêm gói mới. `confluent-kafka` đã có trong `configs/requirements_serving.txt`, được `api.Dockerfile` cài sẵn.
- **Tests:** unit test cho `POST /ratings` và `GET /ratings/{eventId}` dùng producer và repository giả lập. Kiểm thử thật trên stack bằng kịch bản demo.
- **Tài liệu:**
  - `docs/TESTING_GUIDE.md` thêm flow demo bằng giao diện.
  - `docs/SERVING_ARCHITECTURE.md` cập nhật hộp USER APP.
  - `docs/DEPLOYMENT_DESIGN.md` ghi trade-off "API vừa đọc vừa ghi". Production nên tách thành ingestion service riêng.
- **Thời gian:**
  - Giai đoạn A+ khoảng 2 giờ, giai đoạn B khoảng nửa ngày. Làm A+ trước.
  - Lịch: hôm nay 29/09, M8 là 03/10, report §10–12 chưa viết. Nếu hết giờ giữa chừng thì vẫn demo được bằng Swagger. Đây là cách giảm thiểu rủi ro R4 ("overbuilt").
- **Rủi ro demo sống:** Docker Desktop đã tự tắt 2 lần trong quá trình làm. Cần quay sẵn video demo làm phương án dự phòng.
