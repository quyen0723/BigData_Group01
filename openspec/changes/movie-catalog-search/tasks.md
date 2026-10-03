## 1. Chuẩn bị

- [x] 1.1 Đo mốc: số phim trong `movies` (87,585), số phim demo, kết quả thử bằng tay trong Mongo cho "pulp", thể loại Western và 10 phim nhiều rating nhất (để so với API sau này); ghi vào `evidence/p2_movie_search.txt` (87,585 phim; "pulp" 4; Western 1,696; xem `evidence/p2_movie_search.txt`)

## 2. Lõi tìm kiếm (thuần)

- [x] 2.1 `src/serving/catalog.py`: `CatalogEntry`, `search(entries, stats, deltas, q, genre, sort, order, page, size, m, c)` trả (tổng, các dòng): tách từ khoá, lọc thể loại, tính `ratings`, `avg`, `wr`, sắp xếp ổn định (giá trị thiếu nằm cuối cả hai chiều), phân trang; không I/O (`src/serving/catalog.py`)
- [x] 2.2 Test thuần: tìm theo tên (mọi từ, không phân biệt hoa thường), lọc thể loại, từng khoá sắp xếp và chiều, giá trị thiếu nằm cuối, trang vượt quá, phim demo, `q` rỗng; so với tính brute force trên dữ liệu ngẫu nhiên (`tests/unit/test_catalog.py` 16 test, thử 4 đột biến đều bị bắt)

## 3. Backend

- [x] 3.1 Repository: `get_catalog()` (đọc `movies`: id, title, genres, support; `isDemo` suy ra từ dải id) vào Protocol và `FakeServingRepository`; lớp giữ danh mục 30 giây, làm mới ngay khi tạo hoặc xoá phim demo (`create_movie`, `delete_movie`) (`get_catalog`, `CatalogCache` sắp xếp một lần và làm mới nền, làm mới ngay khi tạo/xoá phim demo)
- [x] 3.2 `LivePopularity.snapshot()`: trả (baseline, deltas) dùng chung cache (`m` lấy từ cấu hình `popularity`), không bao giờ ném lỗi, `None` khi thiếu baseline (`LivePopularity.snapshot()`)
- [x] 3.3 Route `GET /movies` trong `src/api/main.py` (gate `require_demo`, tham số theo D-4, 422 khi sai, 422 riêng khi sắp theo `avg`/`wr` mà không có số liệu) và các model trong `schemas.py` (`GET /movies`, 404 trước 422; sắp theo avg/wr khi thiếu baseline trả 422 kèm lý do)
- [x] 3.4 pytest cho từng scenario của `specs/movie-catalog`: tìm, từng từ, thể loại, gate (404 trước 422), tham số sai, số liệu, phim ra sau cutoff, không baseline, sắp xếp, phân trang, phim demo thấy ngay, một lần đọc cho 30 lần tìm (`tests/unit/test_movies_search_api.py` 19 test, 4 đột biến bị bắt; pytest 349)
- [x] 3.5 Sinh lại `schema.d.ts` bằng `npm run gen:api` (API đã restart) và kiểm `tsc` (sinh lại bằng `npm run gen:api`, `tsc` sạch)

## 4. Admin

- [x] 4.1 Hook `useCatalog({ q, genre, sort, order, page })` (TanStack Query, giữ dữ liệu cũ khi đổi trang) và khoá truy vấn; `api.movies(params)` (`api.movies`, `useMovies`)
- [x] 4.2 `web/src/admin/Catalog.tsx`: ô tìm đợi 300 ms, bộ lọc thể loại, chọn sắp xếp và đảo chiều, phân trang, cột theo D-5, "—" có giải thích, trạng thái tải, lỗi có Thử lại, rỗng; đặt dưới `DemoMovies` trong mục `#/movies` (`web/src/admin/Catalog.tsx`, `MoviesSection.tsx`)
- [x] 4.3 Vitest cho mọi scenario của bảng admin; khi thêm hoặc xoá phim demo bảng làm mới (`Catalog.test.tsx` 12 test + `MoviesSection.test.tsx` 2 test, 3 đột biến bị bắt)

## 5. Trang user

- [x] 5.1 `MovieCard`: tuỳ chọn `showRank` (ẩn "#hạng") và dòng "Bạn đã chấm N sao"; cập nhật test thẻ (`showRank`, `ratedStars`; thêm 4 test cho thẻ)
- [x] 5.2 `web/src/user/MovieSearch.tsx`: ô tìm, lọc thể loại, tối thiểu 2 ký tự hoặc có thể loại, 12 kết quả mỗi lần và "Xem thêm", chấm qua `useRatingFlow` của `Home`, "Bạn đã chấm N sao" từ lịch sử, trạng thái rỗng, đặt trong `Home` dưới banner (`web/src/user/MovieSearch.tsx`; toast gọi đúng tên phim tìm được: lỗi do test phát hiện và đã sửa)
- [x] 5.3 Vitest cho mọi scenario của ô tìm user, kể cả: không từ kỹ thuật, chấm xong thì làm mới gợi ý, không gọi API khi chưa đủ điều kiện; `npm run build` còn trong ngân sách và không lẫn mã admin vào trang user (`MovieSearch.test.tsx` 9 test, 4 đột biến bị bắt; Vitest 213; build: app 128.2 KB, admin 150.9 KB gzip)

## 6. Kiểm chứng trên stack thật

- [x] 6.1 Restart `api`, so kết quả `GET /movies` với số đo mốc 1.1 ("pulp", Western, 10 phim nhiều rating nhất); đo thời gian tìm và sắp xếp (mục tiêu dưới 150 ms sau lần nạp đầu) (số liệu khớp mốc; tìm 40–80 ms, sắp xếp toàn bộ 130–250 ms; xem evidence mục 2)
- [x] 6.2 Dựng lại image `api`, kiểm trên trình duyệt: admin tìm "pulp", lọc Western, sắp xếp, đổi trang; trang user tìm "pulp" rồi chấm; phim thêm bằng admin tìm thấy ngay (admin: 87,585 phim, tìm "pulp" ra 4, Western 1,696; `/app`: ô tìm trên "Dành cho bạn", "pulp" ra 4 thẻ, Pulp Fiction hiện "Bạn đã chấm 4,5 sao", không từ kỹ thuật)
- [x] 6.3 Toàn bộ pytest và Vitest pass, không test bị skip hay rỗng; review độc lập (code-reviewer, chỉ đọc) và xử lý các điểm cần sửa (review: 3 cao, 8 vừa, 9 thấp, 5 lệch tài liệu; xử lý ở mục 8; pytest 365, Vitest 217)

## 7. Tài liệu

- [x] 7.1 `docs/TESTING_GUIDE.md`: mục "Test case qua giao diện" dùng ô tìm (các case kiểm hành vi hệ thống, kỳ vọng đã đo); README một dòng; `web/README.md` ghi hai thành phần mới (TESTING_GUIDE mục "Test case kiểm hành vi hệ thống qua giao diện", README dòng "Movie search", web/README mục Layout)
- [x] 7.2 Hoàn thiện `evidence/p2_movie_search.txt` (mục 4: review và số đo sau khi sửa); `openspec validate movie-catalog-search --strict` pass; commit và push chỉ khi người dùng yêu cầu

## 8. Sửa sau review độc lập

- [x] 8.1 Cao: `OrderCache` (mỗi thứ tự sắp xếp tính một lần cho mỗi ảnh chụp dữ liệu, một lần tại một thời điểm); `/movies?sort=wr` 0,6–1,6 s xuống 13–20 ms, `/recommendations` dưới bốn tìm kiếm song song 0,8–1,8 s xuống 0,1–0,28 s
- [x] 8.2 Cao: `snapshot()` có cache theo TTL và đường không chặn như `get()`; `_ledger_deltas` giữ nguyên đối tượng khi nội dung không đổi
- [x] 8.3 Cao: luồng làm mới không khởi động được thì nhả khoá (trước đó khoá bị giữ vĩnh viễn và `invalidate()` treo)
- [x] 8.4 Vừa: `invalidate()` không chờ lần đọc đang chạy (bộ đếm thế hệ); `search()` từ chối `page` và `size` nhỏ hơn 1; log khi làm mới lỗi
- [x] 8.5 Vừa: bảng admin về trang 1 lúc render (không gửi yêu cầu bộ lọc mới với trang cũ), luôn hiện lỗi kể cả sau lần tải đầu thành công, tự về sắp theo số rating khi server trả 422, một nguồn cho số trang, cắt khoảng trắng của ô tìm; không thử lại lỗi 4xx; ô tìm user báo khi tên một ký tự bị bỏ qua vì đã chọn thể loại; items được memo hoá; danh sách tìm không tải lại mọi trang khi quay lại tab
- [x] 8.6 Vừa: `trainRatings` và `newRatings` là số đếm (0, không `null`): sửa spec và design cho khớp code và test
- [x] 8.7 Test: `assume_sorted` (chế độ duy nhất API dùng) cho quy tắc hoà; so với tính brute force ở ba chế độ; `OrderCache` (dùng lại, tính lại khi dữ liệu đổi, đồng thời, giới hạn); thread không khởi động được; `invalidate()` trong lúc làm mới; snapshot (TTL, lỗi, không chờ); 12 đột biến backend đều bị bắt, 6 trong 7 đột biến frontend bị bắt (còn một khung hình lỗi thoáng qua chưa có test, xem evidence mục 4)
