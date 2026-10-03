## Why

Danh sách phim phổ biến hiện là một **artifact tính offline**: Quyên chạy `src/modeling/split_baselines.py` (chia train/val/test theo thời gian, `C` = điểm TB tập train, `m = 1000`), xuất `popular_movies.json`, loader đổ vào Mongo, API chỉ đọc. Weighted rating (WR) đã chạy đúng (đã đo: thứ tự API khớp từng vị trí với file của Quyên; tính lại WR từ số liệu cũ ra đúng các số trong file mới), nhưng khi demo chỉ có thể **mở kết quả có sẵn**. Rating mới qua Kafka và streaming (12–44 giây) không bao giờ làm danh sách này đổi.

Người dùng muốn demo WR **trực tiếp**: chấm rating, danh sách phổ biến đổi theo, và thấy được vì sao công thức này chống được việc spam điểm cao cho phim ít người chấm.

Đã tính trên artifact hiện tại (m = 1000, WR làm tròn 3 chữ số nên số rating dưới đây là ước lượng ±30%):
- **Đổi hạng trực tiếp được ở đúng một cặp.** Hạng 8 Cuckoo's Nest (WR 4.206, v = 33,573) và hạng 9 Seven Samurai (WR 4.205, v = 12,776) cách nhau khoảng 0.001; mỗi rating 5 sao cho Seven Samurai tăng WR 5.8×10⁻⁵, nên cần **khoảng 18 rating** để Seven Samurai vượt lên hạng 8. Các cặp liền kề khác cần từ khoảng 155 (hạng 6–7) đến hàng nghìn rating. Điều này tự nó là bài học về WR: phim càng nhiều rating thì càng "nặng", khó xoay chuyển.
- **WR chống chịu, không miễn nhiễm.** Planet Earth (điểm TB 4.468, v = 173) có WR 3.667; thêm 100 rating 5 sao chỉ đưa lên 3.77, vẫn thấp xa ngưỡng top 10 (4.199). Phải cỡ 780 rating 5 sao (4,5 lần số rating thật của phim) mới vào được top. Demo phải nói đúng điều này, không nói "không bao giờ vào top".

## What Changes

**Cách làm: không sửa streaming.** Ledger `rating_events` đã ghi mỗi rating đúng một lần, sau khi mọi tác động đã áp dụng (`pipeline.py` bước 6). Vì vậy WR sống = **số liệu gốc từ tập train + delta từ ledger**, tính ở API. Đếm bằng bộ đếm do streaming cập nhật bị loại, vì Mongo bản đơn lẻ không có transaction nhiều tài liệu nên crash giữa hai ghi sẽ đếm dư hoặc thiếu (xem design D-1).

**Backend**
- Collection mới `movie_stats` (mỗi phim: `n0`, `sum0` tính từ tập train theo đúng cutoff của Quyên) kèm một tài liệu meta (`C`, cutoff, số rating, thời điểm tạo, `ledgerSince`). Loader mới `loaders/build_movie_stats.py` (Spark, chạy một lần, thay thế an toàn).
- Module thuần `src/serving/popularity.py`: WR, gộp baseline + delta, thứ tự **WR giảm → support giảm → movieId tăng** (giống offline), lọc `min_support` trên v hiện tại.
- Repository đọc baseline (nạp vào bộ nhớ một lần) và delta từ ledger (rating mới nhất của mỗi cặp user-phim), bộ nhớ đệm TTL ngắn.
- `service.get_recommendations` lấy danh sách phổ biến từ nguồn sống khi bật cờ; ngược lại hoặc khi thiếu baseline hoặc lỗi thì dùng artifact như cũ, không bao giờ làm request gợi ý thất bại.
- Khối cấu hình `popularity:` trong `configs/serving.yaml` (`live`, `m`, `min_support`, `top_n`, `cache_ttl_seconds`).
- `GET /debug/popularity` (demo-only): top-N sống kèm điểm TB, số rating gốc, số rating mới, WR, hạng gốc; tham số `m` để **xem trước** WR với m khác (không đổi hệ thống) và `deltas=false` để xem baseline thuần.

**Demo**
- Trang admin thêm mục **Phổ biến** (`#/popularity`): bảng top 10 tự cập nhật, đánh dấu phim vừa đổi hạng, khung "công thức từng bước" cho một phim, ô nhập `m` xem trước.
- `scripts/wr_live_demo.py`: `plan` (tìm cặp phim sát nhau nhất và số rating cần), `inject` (gửi rating từ user giả qua `POST /ratings`, chờ `applied`), `spam` (nhồi 5 sao cho một phim ít người chấm: in WR sau mỗi mốc 10, 100 và số rating cần để vượt ngưỡng top 10), in bảng trước và sau.
- `scripts/purge_demo_ratings.py`: xoá user giả và rating của chúng khỏi Mongo (có `--dry-run`, chỉ chạy trong dải userId giả).

**Giữ nguyên:** streaming, Kafka, schema ledger, `POST /ratings`, các tier few/enough, ALS, content, phim mới, cách API chặn route bằng `demo_enabled`, artifact `popular_movies.json` (vẫn là tham chiếu offline và đường lùi).

**Ngoài phạm vi:** bộ đếm trong streaming (hướng mở rộng khi ledger lớn), thống kê theo thể loại và khung giải thích gợi ý (change `admin-recommendation-explainer`), đổi `m` hay `C` trên hệ thống đang chạy (chỉ xem trước), đổi quy tắc chọn phim mới, quy mô production.

## Capabilities

### New Capabilities
- `live-popularity`: baseline thống kê từ tập train, delta từ ledger, cùng công thức và thứ tự với bản offline, đường lùi về artifact, cấu hình.
- `demo-popularity-live`: endpoint debug, mục admin "Phổ biến", script demo và script dọn dữ liệu giả.

### Modified Capabilities
<!-- openspec/specs/ đang trống (các change trước chưa archive) nên delta viết dạng ADDED trong thư mục cùng tên. Liên quan: recommendation-api (tier 0 và phần đệm popularity), demo-admin-console (thêm mục), rating-ingestion-api (không đổi). Archive sau `rebuild-ui-react`. -->

## Impact

- **Code mới:** `src/loaders/build_movie_stats.py`, `src/serving/popularity.py`, `scripts/wr_live_demo.py`, `scripts/purge_demo_ratings.py`, `web/src/admin/Popularity.tsx` (+ hook, test), test pytest và Vitest.
- **Code sửa:** `src/serving/repository.py` (+ `tests/unit/fakes.py`), `src/serving/service.py`, `src/serving/config.py`, `configs/serving.yaml`, `src/api/main.py` và `schemas.py` (endpoint), `web/src/admin` (route, sidebar), `docs/TESTING_GUIDE.md`, README.
- **Dữ liệu:** collection `movie_stats` (36,526 tài liệu, vài MB) trong Mongo; không đổi collection nào có sẵn.
- **Rủi ro:** (1) tính delta quét ledger, tăng theo số event: ổn ở quy mô demo, bộ đếm là hướng mở rộng; (2) rating giả của buổi demo đi vào ledger, `user_rated` và `curated_ratings` giống mọi rating demo trước đó, và gói bàn giao retrain lấy từ ledger, nên **phải dọn trước khi bàn giao**; (3) danh sách tier 0 giờ đổi theo rating nên test và demo dựa vào thứ tự cố định cần biết; có cờ tắt; (4) nếu Quyên đổi `m`, `C` hay cutoff thì phải chạy lại loader và so khớp (script kiểm có sẵn).
- **Thời gian:** khoảng 1,5–2 ngày. Nhánh tách từ `feat/rebuild-ui-react` vì mục admin mới nằm trên frontend React chưa merge.
