## Why

Buổi họp nhóm 29/09 chốt **bảng 9 use case** trong Google Doc "Notes - BDA501" (tab 5). Bảng mô tả hệ thống phải hành xử thế nào với từng tình huống: user chưa rating, user có rating mới, phim mới, retrain, promote... Kèm theo là ghi chú: *"Dropdown chọn user để chuyển user cho từng case test"*.

Trang `/demo` hiện tại (change `add-demo-web-client`) chỉ có 3 nút preset. Nó phủ được case 1, 2, 7, 8 nhưng còn hai lỗ hổng:
- **Case 3, 4, 9 (phim mới) không thể demo.** Không có cách thêm phim. `POST /ratings` từ chối movieId lạ. Quan trọng hơn, `similar_movies` được tính sẵn, nên một phim mới **không bao giờ** xuất hiện trong gợi ý qua đường content.
- **Case 5, 6 (retrain, promote) không hiện trên trang.** Dữ liệu đã có sẵn trong Mongo (`model_registry` ghi `v1.0.0` active, `v1.1.0` rejected kèm báo cáo gate) nhưng chưa được hiển thị.

M8 là 03/10/2026. Trang demo là nơi giám khảo kiểm chứng các use case này.

## What Changes

**Trang `/demo` tổ chức theo case test**
- Dropdown "Case test" thay cho 3 nút preset, vẫn giữ ô nhập `userId` tự do.
- Mỗi case có một thẻ giải thích lấy đúng các cột của bảng nhóm chốt: *Điều gì xảy ra / Recommendation / Streaming / ALS Retrain / Chốt*.
- Các case: 1 và 7 (chưa rating), 2 (có rating mới), 8 (vài rating đầu tiên), "đã có rating và có ALS", "đủ lịch sử nhưng thiếu ALS" (fallback, không có trong bảng gốc), 3, 4, 9 (phim mới), 5, 6 (retrain/promote).
- User cho case 8 được tạo trước bằng script, gửi rating qua chính `POST /ratings` với `eventId` cố định. Nhờ vậy chạy lại script không tạo trùng.
- Case 1 luôn sinh user mới, vì user bị "tiêu hao" sau khi rate (case 1 chuyển thành case 8).

**Phim mới: làm thật (case 3, 4, 9)**
- `POST /movies` và `DELETE /movies/{movieId}` (demo-only, theo cờ `api.demo_enabled`). Phim demo nhận movieId trong dải riêng từ 9,000,000, thể loại phải thuộc 19 thể loại của MovieLens.
- Nguồn gợi ý mới **`new`**: phim demo khớp thể loại user hay xem (tính từ `positive_movieIds`, nếu rỗng thì dùng `recent_movieIds`). Phim này được chèn vào **một vị trí dành riêng** trong top-k. Áp dụng cho tier few và enough. Tier 0 giữ nguyên popularity như nhóm đã chốt cho case 1.
- Streaming pipeline phải nhận rating cho phim được thêm **sau khi** pipeline đã khởi động. Việc đầu tiên là kiểm chứng điều này, sửa nếu cần.

**Retrain và promote: chỉ hiển thị (case 5, 6)**
- `GET /debug/system` (demo-only) trả về: danh sách version trong `model_registry` (status, thời điểm, tóm tắt gate), version đang active, số event mới tính từ lần bàn giao gần nhất so với ngưỡng `n_min_events`.
- Không có nút kích hoạt, vì việc train chạy trên Colab của Person 1.

**Điều chỉnh nhỏ**
- Thời gian chờ xác nhận rating trên trang tăng từ 30 lên 60 giây và đưa vào config. Lý do: đã đo được độ trễ áp dụng thực tế 42 giây trên máy demo; với 30 giây, trang báo "pending" dù hệ thống vẫn chạy đúng.

**Không đổi:** cách chọn tier, chuỗi hạ cấp `fallbackReason`, weighted RRF của các nguồn hiện có, schema Mongo của các collection cũ, promotion gate.

**Ngoài phạm vi**
- Popularity theo **weighted rating Bayesian/IMDb** (dòng "Chốt" của case 1) giao cho Person 1 (Quyên) nghiên cứu, chọn `m` và xuất lại `popular_movies.json`. Hiện trạng: điểm trung bình thô với `min_support=100`, nên *Planet Earth* (173 rating) đứng trên *Shawshank* (73,945 rating).
- Không làm giao diện onboarding (nhóm đã chốt case 7 = case 1) và không làm LLM re-ranking.

## Capabilities

### New Capabilities
- `demo-case-scenarios`: trang demo theo case test. Gồm dropdown, thẻ giải thích từng case theo bảng của nhóm, user được chuẩn bị sẵn cho từng case, panel vòng đời model và tiến độ retrain (`GET /debug/system`), và thời gian chờ xác nhận rating cấu hình được.
- `new-movie-cold-start`: thêm và xoá phim demo, nguồn gợi ý `new` (phim mới khớp thể loại, có vị trí dành riêng), và yêu cầu streaming nhận rating cho phim thêm sau khi pipeline đã chạy.

### Modified Capabilities
<!-- openspec/specs/ đang trống vì hai change person2-serving-streaming-integration và add-demo-web-client chưa archive, nên không có delta spec. Quan hệ với hai change đó ghi ở mục Impact. -->

## Impact

- **Code:**
  - `src/serving/service.py` + `router.py`: thêm nguồn `new` và bước chèn vị trí dành riêng.
  - `src/serving/repository.py`: thêm đọc phim demo, tạo/xoá phim, đọc `model_registry` và tiến độ retrain.
  - `src/api/main.py` + `schemas.py`: 3 route mới.
  - `src/api/static/demo.html`: dropdown, thẻ case, panel hệ thống, form thêm phim.
  - `src/streaming/pipeline.py`: chỉ sửa nếu bước kiểm chứng cho thấy pipeline không nhận phim mới.
  - `scripts/seed_demo_users.py`: script mới tạo user cho case 8.
- **Config:** `configs/serving.yaml` thêm nhóm `new_items` (bật/tắt, số vị trí, vị trí chèn, dải movieId) và `api.rating_poll_timeout_seconds`. Ngưỡng retrain đọc từ `configs/streaming.yaml` để chỉ có một nơi khai báo.
- **Quan hệ với change chưa archive:**
  - Dropdown vẫn chứa đủ 3 preset cũ và ô nhập `userId`, nên vẫn thoả yêu cầu "User selection" của `add-demo-web-client`.
  - Thời gian chờ 60 giây thay cho mốc 30 giây trong spec của `add-demo-web-client`.
  - Nguồn `new` bổ sung vào "History-tier routing" của `person2-serving-streaming-integration`, không đổi cách chọn tier.
- **Dữ liệu:**
  - Phim demo chỉ nằm trong MongoDB, **không** vào Curated Parquet (`curated_movies`). Rating cho phim demo vẫn được append vào `curated_ratings` như mọi rating khác. Cần báo Person 1 để job retrain không gặp movieId lạ.
  - `bootstrap_registry` kiểm tra `movies == 87,585`, nên phải xoá phim demo trước khi nạp lại.
- **Dependencies:** không thêm gói mới.
- **Rủi ro chính:** bước kiểm chứng streaming. Nếu Spark chỉ đọc bảng `movies` một lần lúc khởi động, rating cho phim mới sẽ bị quarantine nhầm, cần sửa pipeline.
