## Context

**Hiện trạng**
- `/demo` (change `add-demo-web-client`) có 3 nút preset, vòng lặp ⭐ → `POST /ratings` → poll `GET /ratings/{eventId}`, và panel "bên trong hệ thống" lấy dữ liệu từ `GET /debug/users/{userId}`.
- `service.get_recommendations` ([service.py](../../../src/serving/service.py)) dựng gợi ý theo các bước:
  1. đọc con trỏ `serving_meta`;
  2. đọc `user_history` để chọn tier;
  3. lấy các nguồn `als` / `content` / `popularity`;
  4. loại phim đã rate;
  5. trộn bằng weighted RRF;
  6. bù từ popularity cho đủ `k`;
  7. gắn tên phim, thể loại từ `movies`.
- Nguồn `content` đọc `similar_movies`: top-20 phim tương tự được Person 1 **tính sẵn** cho từng phim theo version. Một phim mới không có danh sách riêng và không nằm trong danh sách của phim nào khác.
- `pipeline.py` nạp `movies` từ Mongo **một lần** trong `main()` và broadcast-join vào stream đã parse để kiểm tra luật `unknown_movie_id` ([pipeline.py:294](../../../src/streaming/pipeline.py)).
- `movies` hiện có 87,585 phim, movieId lớn nhất 292,757, chỉ có index `_id`. Có 19 thể loại thật, cộng nhãn `(no genres listed)`.
- `bootstrap_registry` kiểm tra số phim **đúng bằng** 87,585.
- `retrain_trigger.py` đếm `rating_events` có `ingestedAt` sau `pipeline_state.retrain_handoff.watermark` rồi so với `n_min_events` (50) trong `configs/streaming.yaml`.

**Ràng buộc**
- M8 = 03/10/2026, tức còn 2 ngày. Làm theo lớp: phần nào xong là demo được phần đó.
- Demo-only: mọi route mới nằm sau cờ `api.demo_enabled`.
- Không đổi cách chọn tier, chuỗi hạ cấp, trọng số RRF của các nguồn cũ hay schema Mongo cũ.

## Goals / Non-Goals

**Goals:**
- Mỗi case trong bảng nhóm chốt có một lựa chọn trong dropdown, kèm thẻ "kỳ vọng" (theo bảng) đặt cạnh "quan sát thực tế" (theo response).
- Case 3, 4, 9 chạy thật trên stack: thêm phim, phim xuất hiện trong gợi ý của user hợp thể loại, rating cho phim đó đi hết pipeline.
- Case 5, 6 nhìn thấy được từ dữ liệu thật: `model_registry` và tiến độ retrain.

**Non-Goals:**
- Popularity Bayesian/IMDb (Person 1 làm).
- Giao diện onboarding, LLM re-ranking.
- Nút kích hoạt retrain hoặc promote.
- Đưa phim demo vào Curated Parquet (`curated_movies`).
- Tính lại `similar_movies` cho toàn catalog.

## Decisions

### D-1. Danh mục case là dữ liệu tĩnh trong `demo.html`
- Nội dung 9 case là chữ để trình bày, chép từ bảng của nhóm. Đặt thẳng trong một mảng JS của trang.
- **Đã cân nhắc:** cấu hình case phía server qua route hoặc YAML. Bị loại vì thêm route và schema chỉ để chở chữ tĩnh. Sửa chữ thì sửa đúng một file.

### D-2. Chọn user cho từng case

| Case | User |
|---|---|
| 1, 7 | Sinh ngẫu nhiên trong dải 500000–599998, gọi `/debug/users` kiểm tra `interaction_count == 0`, nếu không thì thử lại (tối đa 5 lần) |
| 8, 2, 3, 4 | User seed sẵn `700008`, có 3 rating cho phim Crime/Drama (296, 318, 858) |
| "Có ALS" | user `1` |
| "Thiếu ALS" | user `127249` |
| 9 | User mới như case 1, presenter rate 1 phim Crime/Drama |
| 5, 6 | Không cần user, chỉ hiện panel hệ thống |

- User seed nằm ở dải 7xxxxx để **không trùng** dải ngẫu nhiên 5xxxxx.
- Case 1 phải kiểm tra lại vì các lần test trước đã để lại vài user 5xxxxx có lịch sử (ví dụ 551843).

### D-3. Seed user qua chính `POST /ratings`, `eventId` tất định
- `scripts/seed_demo_users.py` gửi rating qua API, với `eventId = uuid5(namespace, f"{userId}:{movieId}")`.
- **Đã cân nhắc:** ghi thẳng vào `user_rated` / `user_history` trong Mongo. Bị loại vì đi vòng qua pipeline: `curated_ratings` không có dữ liệu, phá nguyên tắc 2 kho nhất quán.
- `eventId` tất định giúp chạy lại script không có tác dụng thêm, nhờ ledger idempotency đã verify từ trước. Script cũng là một minh chứng idempotency.

### D-4. ID phim demo: dải riêng từ 9,000,000
- `movieId` mới lấy từ **bộ đếm chỉ tăng** (`pipeline_state{_id:"demo_movie_seq"}`, cập nhật nguyên tử bằng pipeline update), bắt đầu từ `id_range_start`. Nếu insert bị trùng khoá (ai đó chèn tay id đó) thì lấy số kế tiếp, tối đa 5 lần.
- **Không tính từ `max(_id)` của các phim còn tồn tại.** Cách đó đã được thử trước và sai: sau khi xoá, phim kế tiếp nhận lại đúng id cũ, trong khi rating cho id đó vẫn nằm trong `user_rated` (xoá phim không xoá rating). User đã rate phim cũ sẽ bị coi là đã rate phim mới nên không bao giờ thấy nó, và lịch sử của họ ghi nhận sai.
- Truy vấn "phim demo" là `{_id: {$gte: 9_000_000}}`, dùng **index `_id` có sẵn**, không cần thêm index.
- **Đã cân nhắc:**
  - `max(_id) + 1` trên toàn bảng: lẫn với dải MovieLens, không phân biệt được phim demo.
  - UUID: không dùng được vì `movieId` là `IntegerType` trong schema Spark và trong CONTRACTS. Dải 9,000,000 vẫn nằm trong int32.
- `DELETE` chỉ chấp nhận id trong dải, nên catalog MovieLens không bị xoá qua API.

### D-5. Ghép phim mới theo hồ sơ thể loại của user
- Hồ sơ thể loại: lấy cùng danh sách seed mà nguồn `content` đang dùng (`router.select_seeds`, tối đa 10 phim), tra `movies` để lấy thể loại, đếm tần suất rồi chuẩn hoá thành tỉ lệ.
- Điểm của một phim demo = tổng tỉ lệ của các thể loại nó có trong hồ sơ, nằm trong [0, 1].
- Xếp theo điểm giảm dần, rồi `addedAt` mới nhất, rồi `movieId`.
- "Mới" nghĩa là `addedAt` trong vòng `new_items.window_days` (mặc định 30 ngày).
- Logic thuần (không I/O) đặt ở module riêng `serving/new_items.py`, cùng phong cách với `router.py` và `fusion.py`, để test không cần Mongo.
- **Đã cân nhắc:** tính độ tương tự phim mới với toàn catalog. Tốn kém, và vẫn không đưa được phim mới vào các danh sách `similar_movies` đã tính sẵn.

### D-6. Chèn vào vị trí dành riêng thay vì cộng vào RRF
- Cộng thêm nguồn `new` vào weighted RRF **không đảm bảo phim mới hiện ra**:
  - Doc ALS của mỗi user có 10 phim, đúng bằng `k`. Phim xếp cuối trong ALS có điểm 1/70.
  - Muốn phim mới (đứng đầu nguồn `new`, điểm β/61) vượt mức đó cần β ≥ 0.87.
  - Còn với β ≥ 1, phim mới lại đè lên cả phim ALS tốt nhất.
- Chọn **vị trí dành riêng**: sau khi trộn và bù đủ `k`, đặt tối đa `new_items.slots` (mặc định 1) phim mới bắt đầu từ hạng `new_items.position` (mặc định 3). Các phim còn lại lùi xuống, phim thứ `k` bị đẩy ra.
- Đây là kiểu "freshness slot" phổ biến: kết quả tất định, dễ giải thích ("luôn có 1 chỗ cho phim mới hợp gu"), không làm lệch thứ tự RRF của các nguồn cũ.
- Tier `0_history` **không** chèn, vì nhóm đã chốt case 1 dùng popularity. Case 9 được kể qua rating đầu tiên: có ít nhất 1 tín hiệu sở thích thì hệ thống mới nối được user mới với phim mới.

```
get_recommendations (sau thay đổi)
  pointer → history → tier ─┬─ 0_history ──────────────────────────────▶ popularity (như cũ)
                            └─ few / enough
                                 als / content / popularity (như cũ)
                                 → exclude rated → weighted RRF → fill đủ k
                                 → [MỚI] chọn phim demo khớp hồ sơ thể loại
                                         (bỏ phim user đã rate) → chèn vào hạng 3
                                 → enrich title/genres → response (source "new")
```

### D-7. Streaming nhận phim thêm sau: kiểm chứng trước, sửa sau
- Kỳ vọng: trong Structured Streaming, phần dữ liệu tĩnh của stream-static join **không cache** sẽ được lập kế hoạch lại mỗi micro-batch. Một lần đọc DataSource V2 (Mongo connector) khi đó sẽ truy vấn lại Mongo, tức là thấy phim mới.
- Nhưng điều này **chưa được kiểm chứng** trên đúng phiên bản connector và đúng cách broadcast. Vì vậy task đầu tiên là thử thật: thêm 1 phim vào dải demo bằng mongosh, gửi rating, xem nó được `applied` hay bị quarantine.
- Nếu thất bại, cách sửa dự phòng: chuyển kiểm tra "phim có tồn tại" của nhánh hợp lệ vào `serve_batch`, tra Mongo bằng pymongo mỗi batch, và ghi event không hợp lệ vào thư mục quarantine bằng batch writer.
- Cách tạm khi hết giờ: tạo phim demo **trước khi** khởi động pipeline.

### D-8. `GET /debug/system`: một route chỉ đọc cho case 5/6
- Trả `model_registry` (chỉ lấy tên và kết quả từng gate check, không trả cả model card), `serving_meta`, và tiến độ retrain.
- Tiến độ retrain dùng **đúng truy vấn** của `retrain_trigger.py`, để số trên web bằng số mà trigger thật sẽ thấy.
- `n_min_events` đọc từ `configs/streaming.yaml` qua bộ nạp config, để chỉ có một nơi khai báo.
- **Đã cân nhắc:** chép `n_min_events` sang `serving.yaml`. Bị loại vì hai nơi dễ lệch nhau.
- Route trả thêm `demo.ratingPollTimeoutSeconds` (D-9), để trang chỉ cần gọi một lần khi tải.

### D-9. Thời gian chờ xác nhận rating: 60 giây, cấu hình được
- Đã đo được 12–44 giây (trung vị ~20 giây) khi không có tranh chấp CPU, và 1–4 phút khi có job Spark khác chạy song song. Nguyên nhân chính: hai stream query nối tiếp, mỗi batch ~10 giây (xem `evidence/p2_streaming_latency.txt`). Lời giải thích ban đầu "do `raw_events/` tích nhiều file nhỏ" không được số liệu ủng hộ (chỉ 31 file mà độ trễ lại tốt hơn lúc ít tranh chấp) và đã bị gỡ.
- Mốc 30 giây làm trang báo "pending" dù hệ thống vẫn đúng.
- Đặt `api.rating_poll_timeout_seconds: 60`. Trang dùng 60 nếu không gọi được `/debug/system`.

### D-10. Phim demo chỉ nằm trong MongoDB
- API không có Spark hay pyarrow. Ghi Parquet từ API sẽ ghi đồng thời với Spark.
- Trong production, thêm phim vào catalog đi qua batch ETL vào `curated_movies`. Ở đây route `POST /movies` là lối tắt demo-only, nên ghi rõ giới hạn này.
- Hệ quả:
  - Rating cho phim demo vẫn được streaming append vào `curated_ratings`, nên job retrain của Person 1 có thể gặp `movieId` không có trong `curated_movies`. Cần báo Person 1.
  - Nạp lại bằng `bootstrap_registry` sẽ FAIL vì gate đếm số phim, nên phải xoá phim demo trước.

## Risks / Trade-offs

- **[Kiểm chứng streaming (D-7) thất bại]** → Áp dụng cách sửa dự phòng (khoảng nửa ngày). Nếu không kịp M8: tạo phim demo trước khi khởi động pipeline, và nói rõ giới hạn khi thuyết trình.
- **[User seed bị "tiêu hao": user 700008 bị rate nhiều lần trong lúc demo sẽ vượt T=10, chuyển sang `enough_history`]** → Thẻ case hiện `interaction_count` hiện tại. Script seed có tham số để tạo user mới trong dải 7xxxxx.
- **[Vị trí dành riêng làm người xem tưởng RRF tự xếp phim mới lên hạng 3]** → Thẻ phim có nhãn `new`, và thẻ case giải thích cơ chế "1 chỗ cho phim mới".
- **[Phim demo bị quên trong DB làm FAIL lần nạp lại]** → Có route `DELETE`, và checklist dọn dẹp trong TESTING_GUIDE.
- **[Hồ sơ thể loại rỗng vì user chỉ rate dưới 4 sao]** → Dùng `recent_movieIds` thay thế, giống nguồn `content`.
- **[Thời hạn M8]** → Thứ tự task:
  1. kiểm chứng streaming;
  2. dropdown + panel hệ thống (rủi ro thấp, demo được ngay);
  3. nguồn `new` + route phim;
  4. kiểm thử thật + tài liệu.

  Xong lớp nào là demo được lớp đó.
- **[Đếm `rating_events` theo `ingestedAt` không có index]** → Collection hiện chỉ vài chục doc, chấp nhận ở demo. Ghi chú cần index ở production.

## Migration Plan

1. Thêm config (`new_items.*`, `api.rating_poll_timeout_seconds`), repository, module `new_items.py`, các route. Code `src/` được mount vào container nên chỉ cần `docker compose restart api`.
2. Chạy `scripts/seed_demo_users.py` khi pipeline đang chạy.
3. Bật `api.demo_enabled: true` khi demo.
4. **Rollback:** đặt `new_items.enabled: false` (gợi ý trở lại y như cũ), xoá phim demo bằng `DELETE /movies/{id}`, tắt `demo_enabled`. Không có migration dữ liệu.

## Open Questions

- Vị trí chèn mặc định 3 hay 1? Hạng 1 nổi bật nhất khi demo, nhưng đè lên gợi ý cá nhân hoá tốt nhất.
- Cửa sổ "phim mới" 30 ngày có hợp lý không, hay giữ phim demo là "mới" cho tới lần retrain tiếp theo?
- Person 1 muốn xử lý thế nào với `movieId` từ dải demo xuất hiện trong `curated_ratings`? Lọc bỏ khi retrain, hay muốn có thêm file catalog phụ?
