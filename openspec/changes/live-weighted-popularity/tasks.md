## 1. Chuẩn bị

- [x] 1.1 Tạo nhánh `feat/live-weighted-popularity` từ `feat/rebuild-ui-react` (mục admin mới nằm trên frontend React chưa merge); chạy pytest và Vitest làm mốc (kỳ vọng 185 và 162 pass)
- [x] 1.2 Tạo `evidence/p2_live_wr.txt`; ghi các số đo mốc: thứ tự và WR top 10 hiện tại, số event trong ledger, số tài liệu `user_rated`/`user_history` của dải user giả, kích thước ledger (ledger 55 event; 8 user giả)

## 2. Baseline từ tập train

- [x] 2.1 `src/loaders/build_movie_stats.py` (cùng khuôn `build_movies.py`): đọc cutoff và `n_train` từ `evidence/split_stats.csv` (có `--cutoff` ghi đè), gộp `n0`, `sum0` theo `movieId` từ `curated_ratings` với `timestamp < cutoff`, ghi `movie_stats` bằng `write_collection(..., operation_type="replace")`, rồi ghi tài liệu `_meta` (`C`, `cutoff`, `ratings`, `movies`, `generatedAt`, `ledgerSince`; tham số `--ledger-since`) (`src/loaders/build_movie_stats.py` + phần thuần `movie_stats_core.py`; có `--dry-run`, `--cutoff`, `--ledger-since`; xoá `_meta` trước khi ghi, ghi `_meta` sau cùng, kiểm số tài liệu)
- [x] 2.2 Hai cổng kiểm trước khi ghi: tổng rating bằng `n_train`, điểm TB toàn cục bằng `C` đã ghi ở 4 chữ số; sai thì thoát lỗi và không ghi gì; pytest cho phần tính toán thuần (hàm tách khỏi Spark) (`tests/unit/test_movie_stats_core.py`, 6 test, đọc cả hai file evidence thật)
- [x] 2.3 Chạy loader trong container `spark` (đo thời gian, không chạy lúc streaming đang bận); ghi vào evidence: số phim, `ratings`, `C`, thời gian, và xác nhận Shawshank `n0` = 73,945 (dry-run rồi chạy thật: 22,399,368 rating trên **36,526 phim**, mean 3.528684, 119 giây; Shawshank n0 = 73,945)

## 3. Lõi tính toán thuần

- [x] 3.1 `src/serving/popularity.py`: `weighted_rating`, `rank_top(baseline, deltas, m, c, min_support, n)` với thứ tự WR giảm → v giảm → movieId tăng và lọc `v ≥ min_support`, `deltas_from_events` (cặp user-phim mới nhất, mốc `ledgerSince`); kiểu dữ liệu nhỏ, không phụ thuộc Mongo
- [x] 3.2 Test so với tính brute force trên dữ liệu ngẫu nhiên (thứ tự, tie-break, lọc support); `m = 0` ra điểm TB thô; `v` rất lớn thì WR tiến về R; ví dụ Seven Samurai và Planet Earth trong `specs/live-popularity` (`tests/unit/test_popularity.py`, 16 test; thử đột biến: 3/4 bị bắt, đột biến còn lại tương đương vì cần hai event cùng `_id`)
- [x] 3.3 Đo thời gian `rank_top` với 80 nghìn phim (mục tiêu ≤ 50 ms): trung vị 14 ms (không delta), 21 ms (50 phim có delta), 18 ms cho n = 200; `deltas_from_events` 10 nghìn event 18 ms. Không cần tối ưu thêm

## 4. Repository, cấu hình, service

- [x] 4.1 `PopularityConfig` trong `src/serving/config.py` và khối `popularity:` trong `configs/serving.yaml` (`live: false` trong code khi thiếu khối; kiểm giá trị: `m ≥ 0`, `min_support ≥ 1`, `1 ≤ top_n ≤ 50`, `cache_ttl_seconds ≥ 0`); pytest cho mặc định, thiếu khối và giá trị sai (`PopularityConfig`, `_popularity_config` báo đúng tên khoá; `movie_stats` thêm vào `mongo.collections`)
- [x] 4.2 Repository: `get_movie_stats()` (nạp vào bộ nhớ một lần, tải lại khi `_meta.generatedAt` đổi, bỏ qua `_meta`) và `get_rating_deltas(ledger_since)` (pipeline D-1, `allowDiskUse`); thêm vào Protocol và `FakeServingRepository` (`tests/unit/fakes.py`) (`MongoServingRepository.get_movie_stats/get_rating_deltas` đã chạy trên Mongo thật: pipeline == `deltas_from_events`, xem evidence mục 2)
- [x] 4.3 Lớp nguồn sống trong `popularity.py` hoặc module riêng: cache TTL theo (`m`, `deltas`), một khoá chống làm mới đồng thời, giữ kết quả tốt gần nhất 60 giây khi lỗi, cảnh báo tối đa một lần mỗi phút mỗi nguyên nhân (`src/serving/live_popularity.py`: cache theo (m, deltas, n) có chặn 32 khoá, một khoá làm mới, kết quả lỗi cũng nhớ một TTL, giữ kết quả tốt 60 giây)
- [x] 4.4 `service.get_recommendations`: lấy danh sách phổ biến qua nguồn sống khi bật cờ, ngược lại hoặc khi thiếu baseline hoặc lỗi thì dùng artifact; pytest mọi scenario của `specs/live-popularity` (danh sách sống cho tier 0, tier khác không đổi, cờ tắt, thiếu baseline, lỗi ledger, không bao giờ lỗi request); các test cũ của `service` vẫn pass khi cờ tắt (`tests/unit/test_live_popularity.py`, 28 test; thử 4 đột biến đều bị bắt; toàn bộ pytest 251 pass)
- [x] 4.5 Test delta ở lớp repository giả: cặp (user, phim) trùng chỉ đếm bản mới nhất, `ledgerSince` loại event cũ, event ngoài baseline bắt đầu từ `n0 = 0` (trong `test_popularity.py` và `test_live_popularity.py`)

## 5. Endpoint debug

- [x] 5.1 `GET /debug/popularity` trong `src/api/main.py` (gate `demo_enabled`, tham số `n`, `m`, `deltas`, 422 khi sai) và các model trong `schemas.py`; `baseRank` tính từ thứ tự baseline cùng `m` (null ngoài top 200) (thêm `liveEnabled` vào phản hồi: endpoint chạy được cả khi `popularity.live` còn tắt, phục vụ bước kiểm 8.1)
- [x] 5.2 pytest cho từng scenario của `specs/demo-popularity-live` về endpoint (có số liệu, xem trước `m=0` không đổi `/recommendations`, `deltas=false`, demo tắt, tham số sai, nguồn artifact) (`tests/unit/test_popularity_api.py`, 16 test; 3 đột biến bị bắt)
- [x] 5.3 Sinh lại `web/src/shared/api/schema.d.ts` bằng `npm run gen:api` (API đang chạy) và kiểm `tsc` (schema.d.ts +113 dòng; `tsc` sạch)

## 6. Mục admin "Phổ biến"

- [x] 6.1 Hook `usePopularity({ m })` (TanStack Query, `refetchInterval` 3 giây, tắt khi tab ẩn hoặc mục không mở) và khoá truy vấn trong `shared/api/keys.ts` (`usePopularity` trong `shared/hooks/queries.ts`, `api.popularity`, `keys.popularity`)
- [x] 6.2 `Popularity.tsx`: bảng top 10 (hạng, phim, R, v với "+n mới", WR, thay đổi hạng bằng mũi tên và chữ), dải thông báo nguồn artifact, ô `m` "Xem trước, không đổi hệ thống" kèm thông báo; thêm vào `route.ts`, sidebar và `App.tsx` (`web/src/admin/Popularity.tsx`; mục `#/popularity` tên "Phổ biến" trong sidebar và lối tắt ở Tổng quan; logic thuần ở `popularityLogic.ts` vì `popularity.ts` đụng `Popularity.tsx` trên Windows)
- [x] 6.3 Khung công thức từng bước cho dòng được chọn (thay số, trọng số `v/(v+m)` bằng lời); hiệu ứng đổi hạng tôn trọng `prefers-reduced-motion`; vùng bấm 44 px, mọi điều khiển có tên (khung công thức chọn bằng nút trên tên phim, `aria-pressed`; dấu đổi hạng có mũi tên và chữ, không hiệu ứng chuyển động; vùng bấm 44 px)
- [x] 6.4 Vitest: mọi scenario của mục admin (đổi hạng hiện mũi tên và chữ, ngừng gọi API khi ẩn, khung công thức khớp bảng, xem trước `m`, nguồn artifact); `npm run build` vẫn trong ngân sách và không lẫn mã admin vào trang user (`Popularity.test.tsx` 12 test + `popularityLogic.test.ts` 12 test; thử 3 đột biến đều bị bắt; Vitest 186 pass; build: app 126.7 KB, admin 149.0 KB gzip, 0 module admin trong trang user; nâng `testTimeout` lên 15 giây vì test hộp thoại chạm 5 giây khi cả bộ chạy song song)

## 7. Script demo và dọn dữ liệu

- [x] 7.1 `scripts/wr_live_demo.py` (chỉ thư viện chuẩn) với `check`, `plan`, `inject`, `spam`, `--api`, `--dry-run`; user giả từ 999200001, bỏ qua user đã có lịch sử, eventId `uuid5`, thử lại cùng eventId khi 503, chờ `applied`, in bảng trước và sau kèm đổi hạng (`scripts/wr_live_demo.py`: `check`, `plan`, `inject`, `spam`; `--api` và `--dry-run` dùng được trước hoặc sau lệnh; chạy thử trên API thật: `check` PASS, `plan` ra cặp hạng 9/8 cần **17** rating)
- [x] 7.2 pytest cho phần thuần của script (tính số rating cần để vượt, chọn user, eventId ổn định, định dạng bảng) và cho `--dry-run` không gửi gì (`tests/unit/test_wr_live_demo.py`, 20 test, API giả dùng đúng `rank_top` của hệ thống; thử đột biến: 4 bị bắt, đột biến sai số một đơn vị của công thức đóng là tương đương vì có vòng kiểm tra biên)
- [x] 7.3 `scripts/purge_demo_ratings.py`: xoá `rating_events`, `user_rated`, `user_history` của dải user, mặc định dry-run, `--yes` mới xoá, từ chối dải ngoài 999,000,000–999,999,999; pytest bằng Mongo giả hoặc hàm thuần (`scripts/purge_demo_ratings.py` + luật dải dùng chung `src/loaders/synthetic_users.py`; `tests/unit/test_purge_demo_ratings.py` 10 test; dry-run thật trên Mongo: 8 / 8 / 8 tài liệu)
- [x] 7.4 Viết thủ tục dọn phân vùng `year=2026` của `curated_ratings` (lọc rồi ghi lại), chạy thử một lần trên bản sao thư mục; chỉ thực hiện thật khi người dùng yêu cầu (`src/loaders/purge_curated_synthetic.py`: job Spark viết lại phân vùng `year=2026`, mặc định dry-run, `--apply` bắt buộc kèm `--streaming-stopped`, giữ bản cũ `_purge_old_year=2026`; diễn tập trên bản sao: 55 → 47 rating, hai trường hợp từ chối đúng; phân vùng thật chỉ chạy dry-run: 55 rating, 8 của 8 user giả; chưa dọn thật)

## 8. Kiểm chứng trên stack thật

- [x] 8.1 Với `popularity.live` còn tắt: `wr_live_demo.py check` đạt (baseline-only khớp `artifacts/popular_movies.json`: cùng thứ tự, WR chênh ≤ 0.0005); ghi kết quả (PASS, chênh WR lớn nhất 0.00037)
- [x] 8.2 Đo độ trễ làm mới (80 nghìn phim, ledger hiện có và ledger nhân lên 10 nghìn event tổng hợp trên bản sao) và độ trễ `/recommendations` tier 0 trước và sau; mục tiêu làm mới ≤ 100 ms, không tăng quá 20 ms cho request (làm mới: 24 ms với ledger thật, 121 ms với 10 nghìn event, 1,07 giây với 100 nghìn; `/recommendations` tier 0: trung vị 23–32 ms bật so với 35 ms tắt, không tăng; xem evidence mục 4)
- [x] 8.3 Bật `live: true`, restart `api`: tier 0 vẫn trả đúng top 10 khi ledger chỉ có event demo cũ; `/debug/popularity` hiện `source = live`; ghi vào evidence (cùng top 10 với artifact, `source = live`)
- [x] 8.4 `plan` rồi `inject` 20 rating 5 sao vào Seven Samurai: đổi hạng 8–9 xuất hiện trên bảng admin trong vài giây sau khi `applied`, `/recommendations` của user mới đổi theo; ghi thời gian từ gửi đến đổi hạng (19 rating, áp dụng sau 51 giây: Seven Samurai hạng 9 → 8, WR 4.2054 → 4.2065; user mới nhận đúng thứ tự mới; bảng admin đổi theo)
- [x] 8.5 `spam` trên Planet Earth: +10 và +100 rating vẫn ngoài top 10 (WR khoảng 3.68 và 3.77); in số rating cần để vượt (khoảng 780); không chạy mốc đó trừ khi cần (Planet Earth +10 → WR 3.6791 đúng kế hoạch 3.679, ngoài top 10; mốc 100 và 780 chỉ tính, không gửi)
- [x] 8.6 Đường lùi: tắt `live`, thiếu `movie_stats` (đổi tên tạm), ngắt Mongo giả lập qua lỗi ledger: `/recommendations` luôn 200 và về danh sách artifact; khôi phục sau mỗi thử (mất baseline → artifact, một cảnh báo, 200; cờ tắt → thứ tự artifact; lỗi đọc ledger chỉ kiểm bằng unit test vì không thể gây lỗi ledger thật mà không phá streaming)
- [x] 8.7 Log `streaming` không có lỗi mới trong suốt các bước trên; `streaming` vẫn `healthy` (healthy, RestartCount 0, log sạch, đúng 19 và 10 dòng mới)
- [x] 8.8 Dọn: chạy `purge_demo_ratings.py` (dry-run rồi `--yes`) cho dải 999200000–999299999, kiểm `newRatings` giảm đúng số rating giả; ghi số user giả cũ (999100001–999100010) và user 553438 còn lại để người dùng quyết định (xoá 29 user giả; bảng về thứ tự gốc; còn lại 8 user giả cũ 999100001..10, user 553438 và các dòng parquet để bạn quyết định)
- [x] 8.9 Toàn bộ pytest và Vitest pass, không test bị skip hay để trống; `npm run build` và script kiểm đạt (pytest 313, Vitest 186 / 23 file, tsc sạch, build PASS; không TODO, skip hay test rỗng)
- [x] 8.10 Review độc lập (agent code-reviewer, chỉ đọc) và xử lý các điểm cần sửa (reviewer chỉ đọc: 3 cao, 9 trung bình, 7 thấp; tất cả đã kiểm và sửa trừ M9 là việc dọn dữ liệu còn mở và L7 là quy ước của dự án; xem evidence mục 5)

## 9. Chuyển đổi và tài liệu

- [x] 9.1 Đặt `popularity.live: true` trong `configs/serving.yaml` (giá trị được commit); thử rollback `false` rồi đặt lại `true` (`popularity.live: true` nằm trong bản làm việc và sẽ vào commit; `demo_enabled: true` chỉ là cờ cục bộ, commit đưa bản `false` vào index; đã thử rollback `false` rồi `true`, evidence mục 4)
- [x] 9.2 `docs/TESTING_GUIDE.md`: mục "Demo WR sống" (chuẩn bị baseline, các bước `check`/`plan`/`inject`/`spam`, kỳ vọng đã đo, nói rõ WR chống chịu chứ không miễn nhiễm, dọn dữ liệu, **phải dọn ledger trước khi bàn giao retrain**); README (một dòng về `movie_stats` và cờ); cập nhật text thẻ case 1 và 7 nhắc tới WR sống (TESTING_GUIDE mục "Demo WR sống", README, `web/README.md`, thẻ case 1 nhắc WR sống)
- [x] 9.3 Thông báo cho Quyên (bản nháp trả lời, không đăng): chế độ sống dùng cutoff, `C`, `m`, `min_support` của cô ấy; `popular_movies.json` mới chỉ có tác dụng nếu dựng lại baseline; mô tả quy ước dải user giả (`docs/DRAFT_reply_to_Quyen_live_wr.md`, chưa đăng, không commit)
- [x] 9.4 Hoàn thiện `evidence/p2_live_wr.txt`; `openspec validate live-weighted-popularity --strict` pass; commit và push chỉ khi người dùng yêu cầu (evidence mục 1–5; `openspec validate live-weighted-popularity --strict` pass; chưa commit, chờ người dùng yêu cầu)
