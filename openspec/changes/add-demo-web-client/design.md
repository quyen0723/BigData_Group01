## Context

**Hiện trạng**
- Recommendation API (`src/api/main.py`) chỉ có 2 route đọc: `GET /health` và `GET /recommendations/{userId}`.
- Rating chỉ vào hệ thống qua CLI `streaming.producer`, chạy trong container `spark` và produce thẳng vào Kafka `ratings.v1`.
- Phía sau đã verify thật:
  - Structured Streaming: validate → dedup → `serve_batch`.
  - Mongo: `user_rated`, `user_history`, ledger `rating_events`.
  - Curated Parquet được append thêm.
- Service `api` trong `docker/docker-compose.yml` chỉ nối Mongo. Không có biến Kafka, không `depends_on: kafka`.
- Image `api` đã có sẵn `confluent-kafka`, vì cài chung `configs/requirements_serving.txt`.

**Ràng buộc**
- Demo chạy trên laptop Windows + Docker Desktop, không đảm bảo có internet ổn định lúc thuyết trình. Docker Desktop đã tự tắt 2 lần trong quá trình làm.
- PRD §3.2 non-goal: không xây "Netflix clone". Client phải tối thiểu và dán nhãn **demo-only**.
- Lịch: M8 là 03/10, report §10–12 chưa viết. Phải làm được theo từng lớp, hết giờ ở lớp nào cũng dùng được lớp đó.

## Goals / Non-Goals

**Goals**
- Lấp hộp "USER APP" trong sơ đồ kiến trúc bằng một client bấm được trên trình duyệt, đi **qua API** giống app thật. Không được đọc thẳng Mongo.
- Làm cho các cơ chế đã verify nhìn thấy được khi demo:
  - đổi tier;
  - fresh-history exclusion;
  - idempotency;
  - tính bất đồng bộ / eventual consistency;
  - chuỗi hạ cấp `fallbackReason`.
- Không sửa gì ở streaming pipeline, validation phía streaming, schema Mongo hay router.

**Non-Goals**
- Đăng nhập/xác thực: user chọn bằng cách nhập `userId`.
- Tìm kiếm phim, poster phim, giao diện đẹp kiểu sản phẩm.
- Điều khiển Docker từ trình duyệt. Bước "tắt/bật streaming" trong kịch bản demo vẫn làm bằng terminal.
- Tách ingestion service riêng. Chỉ ghi lại như hướng production, không làm.

## Decisions

### D-1. Route ghi nằm chung FastAPI app hiện tại
- `POST /ratings` và `GET /ratings/{eventId}` thêm vào `src/api/main.py`, dùng chung process với route đọc.
- **Phương án đã cân nhắc: tách "rating ingestion service" riêng.** Đúng hướng production, vì đường đọc và đường ghi có nhu cầu scale khác nhau. Nhưng cần thêm container và thêm cấu hình, không đáng cho demo.
- Trade-off này ghi vào `docs/DEPLOYMENT_DESIGN.md` để có sẵn câu trả lời khi giám khảo hỏi.

### D-2. `POST /ratings` trả **202 Accepted**, không đợi áp dụng
- API chỉ xác nhận event **đã nằm bền vững trong Kafka**. Việc áp dụng do Structured Streaming làm sau. Ghi chú sửa (01/10): thiết kế ban đầu ước tính 5–10 giây, nhưng đo thật là 12–44 giây (trung vị ~20 giây), vì event đi qua hai stream query nối tiếp, mỗi batch ~10 giây (xem `evidence/p2_streaming_latency.txt`).
- **Đã cân nhắc (a): trả 200 và chờ đồng bộ tới khi áp dụng xong.**
  - Latency của API bị buộc vào chu kỳ batch streaming.
  - Che mất bản chất bất đồng bộ của kiến trúc, mà đây lại là thứ cần demo.
- **Đã cân nhắc (b): API ghi thẳng vào Mongo, bỏ qua Kafka.**
  - Phá kiến trúc: mất bước append Curated Parquet, mất ledger idempotency, mất khả năng replay.
  - Demo sẽ thể hiện sai hệ thống thật.

### D-3. `GET /ratings/{eventId}` biến bất đồng bộ thành thứ nhìn thấy được
- Route tra `rating_events` theo `_id = eventId`:
  - có bản ghi → `{status: "applied", batchId, ingestedAt}`;
  - chưa có → `{status: "pending"}`.
- **Giới hạn đã biết:** ledger chỉ ghi event đã áp dụng. Event nằm trong quarantine thì ở Parquet, API không tra rẻ được. Vì vậy "pending mãi" có thể là 1 trong 3 trường hợp:
  - streaming chưa chạy;
  - event bị quarantine;
  - Kafka chưa nhận.
- Giới hạn này chấp nhận được, vì validation phía API (D-4) đã chặn gần hết lỗi định dạng trước khi vào Kafka.
- UI hiển thị gợi ý chẩn đoán khi hết thời gian chờ (D-8). Chính trường hợp "pending vì streaming chưa chạy" là một bước trong kịch bản demo fault tolerance.

### D-4. Validation 2 lớp (defense-in-depth)
- **Lớp API** kiểm tra để trả 422 ngay cho client:
  - `userId > 0`;
  - `rating ∈ VALID_RATINGS`, tái dùng hằng số từ `streaming/events.py`;
  - `movieId` tồn tại, bằng 1 point read `movies._id` (collection đã có, 87,585 docs);
  - `eventId`, nếu client gửi, là chuỗi không rỗng và ≤ 64 ký tự.
- **`timestamp` do API gán** bằng thời điểm server nhận. Client không gửi được timestamp tuỳ ý, nên loại luôn lỗi `invalid_timestamp` khỏi đường UI.
- **Lớp streaming giữ nguyên, không bỏ.** Kafka còn nhận event từ producer khác không qua API, như CLI simulator. Ghi rõ trong spec.

### D-5. Ai tạo `eventId`
- Client **được phép** gửi `eventId`. Trang demo sinh bằng `crypto.randomUUID()` mỗi lần bấm, và dùng lại đúng `eventId` đó nếu phải gửi lại.
- API tự sinh UUID4 nếu client không gửi.
- Nhờ vậy bấm ⭐ 2 lần vì mạng lag vẫn chỉ tính 1 lần, nối thẳng vào cơ chế idempotency đã verify ở streaming.

### D-6. Kafka producer trong API: tạo lười, `flush` có timeout
- Mỗi process API có 1 producer, tạo ở lần `POST` đầu tiên, giống `get_repository()`.
- Cấu hình `acks=all` và `enable.idempotence=True`, tái dùng `streaming/producer.py::make_producer`.
- Mỗi request gọi `produce` rồi `flush(timeout)` và kiểm tra delivery report:
  - thành công → 202;
  - thất bại hoặc hết timeout → **503** kèm lý do.
- Vì vậy "202" có nghĩa thật: đã được Kafka xác nhận với `acks=all`.
- Producer đi qua dependency injection (`get_producer`), test có thể thay bằng producer giả.
- **Đã biết từ phiên trước:** lần produce idempotent đầu tiên sau khi Kafka khởi động có thể gặp `Coordinator load in progress` và tự retry. `flush` timeout đặt 10 giây để hấp thụ.

### D-7. Không thêm `depends_on: kafka` cứng cho service `api`
- Chỉ thêm biến `KAFKA_BOOTSTRAP_SERVERS=kafka:9092`. Producer tạo lười (D-6) nên:
  - Kafka chết thì `GET /recommendations` **vẫn phục vụ bình thường**, chỉ `POST /ratings` trả 503;
  - đường đọc không bị ràng buộc vào hạ tầng của đường ghi.
- Đây là một điểm availability để nói trong phần CAP.
- **Đã cân nhắc:** `depends_on: kafka: service_healthy`. Đơn giản hơn, nhưng Kafka lỗi thì API không khởi động được, kể cả phần đọc.

### D-8. Trang `/demo`: 1 file HTML tĩnh, **không phụ thuộc internet**
- `GET /demo` trả `src/api/static/demo.html` bằng `FileResponse`.
- Vanilla JS và CSS inline: **không CDN, không font ngoài, không poster TMDB**, vì lúc thuyết trình có thể mất mạng. Thẻ phim là thẻ chữ tô màu theo thể loại chính.
- **Bố cục chia đôi:**
  - Trái: ô nhập `userId`.
    - 3 nút preset: *User mới* (sinh `5xxxxx` ngẫu nhiên), *User 1 (có ALS)*, *User 127249 (cold-start)*.
    - Lưới thẻ gợi ý, mỗi thẻ có ⭐ 1–5 (sao nguyên, rating 1.0–5.0).
  - Phải: `tier`, `strategy`, `fallbackReason`, `modelVersion`, latency lấy từ response, cùng `interaction_count` và batch streaming gần nhất từ `/debug`.
  - Nhật ký sự kiện có mốc thời gian.
- **Luồng khi bấm ⭐:**
  1. `POST /ratings`, nhật ký ghi "→ Kafka ✓ (202, eventId …)".
  2. Poll `GET /ratings/{eventId}` mỗi 1 giây, tối đa 30 giây.
  3. `applied` → tự tải lại gợi ý và panel, **đánh dấu thay đổi** (tier đổi, phim vừa rate biến mất).
  4. Hết 30 giây vẫn `pending` → nhật ký hiện gợi ý "Streaming pipeline có đang chạy không?".
- **Đã cân nhắc:**
  - Streamlit: thêm container, dễ bị cám dỗ đọc thẳng Mongo.
  - React/Vite: build tooling, CORS, và chạm vào non-goal "Netflix clone".

### D-9. `GET /debug/users/{userId}`: demo-only, bật bằng config
- Trả:
  - `user_history`: `interaction_count`, `recent_movieIds`, `positive_movieIds`, `lastUpdated`;
  - `pipeline_state.ratings_stream`: `lastBatchId`, `lastRunAt`;
  - `serving_meta`: `modelVersion` đang active.
- Chỉ hoạt động khi `configs/serving.yaml` có `api.demo_enabled: true`, nếu không trả 404.
- **Bảo mật:** route này lộ lịch sử xem phim của user. `userId` đã ẩn danh theo PRD, nhưng vẫn **tắt mặc định ở production**. Ghi vào `DEPLOYMENT_DESIGN.md` §Security.
- `/demo` cũng chỉ phục vụ khi cờ này bật.

## Risks / Trade-offs

- **[Docker Desktop tự tắt giữa buổi demo]** → Quay sẵn video toàn bộ kịch bản demo làm phương án dự phòng. Kiểm tra `docker compose ps` ngay trước giờ thuyết trình.
- **[Pending mãi vì streaming chưa chạy]** → UI hiện gợi ý chẩn đoán (D-8). Biến điểm yếu thành bước demo fault tolerance: tắt streaming, rate, không đổi gì, bật lại, tự bắt kịp.
- **[API vừa đọc vừa ghi — trộn trách nhiệm]** → Chấp nhận ở phạm vi demo, ghi hướng tách service trong `DEPLOYMENT_DESIGN.md`.
- **[Latency `POST` tăng vì `flush` chờ `acks=all`]** → Khoảng chục đến vài trăm ms, chấp nhận được cho thao tác rate. Đổi lại "202" là cam kết thật.
- **[Lần produce đầu sau khi Kafka khởi động bị chậm]** → Timeout `flush` 10 giây. UI hiện "đang gửi…" thay vì treo im lặng.
- **[Trượt phạm vi thành "Netflix clone"]** → Giữ 1 file HTML, không tìm kiếm, không poster. Dán nhãn "Demo web client — demo-only" trên trang và trên sơ đồ.
- **[Hết giờ trước M8]** → Làm theo lớp. Giai đoạn A+ (route ghi + status) đã đủ demo bằng Swagger. Giai đoạn B chỉ bổ sung.

## Migration Plan

1. Thêm route và cấu hình (giai đoạn A+). Recreate service `api`: `docker compose up -d api`. Code `src/` được mount nên không cần rebuild image.
2. Kiểm thử qua Swagger `/docs`: `POST /ratings` rồi `GET /ratings/{eventId}` chuyển `pending → applied`.
3. Thêm `demo.html` và `/debug` (giai đoạn B). Bật `api.demo_enabled: true`.
4. **Rollback:** thay đổi thuần bổ sung. Đặt `api.demo_enabled: false` để ẩn `/demo` và `/debug`. Muốn gỡ hẳn thì xoá các route mới. Không có migration dữ liệu.

## Open Questions

- Sao nguyên 1–5 (mặc định) hay cho phép nửa sao 0.5? Nửa sao khớp đủ tập `VALID_RATINGS` nhưng UI phức tạp hơn.
- Có cần `GET /movies?q=` để tìm phim ngoài danh sách gợi ý không? Mặc định **không** (stretch). Nếu làm thì cần text index trên `movies.title`.
