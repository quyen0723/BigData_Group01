## 1. API: lịch sử đánh giá và route trang

- [x] 1.1 `ServingRepository` + `MongoServingRepository` + `FakeServingRepository`: `get_rating_history(user_id, limit)` — đọc `user_history.recent_movieIds` (mới nhất trước), lấy số sao bằng một truy vấn `$in` trên `user_rated`, tên/thể loại từ `movies`; phim không còn trong `movies` trả `inCatalog: false` (D-6)
- [x] 1.2 `schemas.py`: `RatedMovieOut {movieId, title, genres, rating, inCatalog}`, `RatingHistoryOut {userId, total, items}`
- [x] 1.3 `GET /users/{userId}/ratings?limit=` (mặc định 20, 1–50; 422 sai tham số, không chạm store; 404 khi cờ demo tắt, dùng `require_demo`)
- [x] 1.4 `GET /app` (FileResponse `app.html`) và `GET /admin` (cùng `demo.html` với `/demo`), 404 khi cờ tắt
- [x] 1.5 Unit test: lịch sử đúng thứ tự mới nhất trước và đúng số sao; `limit`; user chưa có lịch sử → `total 0`, `items []`; phim đã xoá → `inCatalog false`; 422 không gọi repository; 404 cho cả 4 route khi cờ tắt; `/admin` và `/demo` trả cùng trang

## 2. Trang người dùng `/app`

- [x] 2.1 Khung trang + hệ thống thị giác D-8 (token màu, font hệ thống, SVG nội tuyến, `:focus-visible`, `prefers-reduced-motion`, vùng `aria-live` cho toast), không tài nguyên ngoài
- [x] 2.2 Màn chọn tài khoản: 3 persona (An 700008, Bình 1, Chi 127249) mô tả theo gu + số rating lấy từ API; dòng "tài khoản demo, không mật khẩu"; lối vào Quản trị
- [x] 2.3 Tạo tài khoản: ô tên có label (1–40 ký tự, lỗi hiện cạnh ô), chọn userId có `total == 0` (≤5 lần), lưu `localStorage` (try/catch); phiên theo tab bằng `sessionStorage` (D-2, D-3); Đăng xuất
- [x] 2.4 Feed "Dành cho bạn": skeleton khi tải, thẻ phim (tên, thể loại, nhãn lý do theo D-4, huy hiệu "Mới"), không lộ thuật ngữ kỹ thuật
- [x] 2.5 Chấm sao: sao 40×40 px (44 px dưới 600 px) có `aria-label`; toast tự tắt 4 s + trạng thái "Đang cập nhật gợi ý…" trên thẻ tới khi `applied`; hết hạn chờ / lỗi 503 theo D-5
- [x] 2.6 Mục "Phim bạn đã đánh giá" (tối đa 50, kèm tổng số) và trạng thái rỗng mời chấm phim cho tài khoản mới
- [x] 2.7 Tự tải lại gợi ý khi tab hiện lại (`visibilitychange`, D-7)

## 3. Sửa trang quản trị (`demo.html`)

- [x] 3.1 Đổi tiêu đề thành "Quản trị", thêm lối sang `/app`
- [x] 3.2 Dưới 900 px: panel phải xếp xuống dưới, không tràn ngang ở 375 px
- [x] 3.3 Sao ≥ 40×40 px có `aria-label`; nút chính `#2563EB`; label cho `userIdInput` và `movieTitle`; nhật ký `aria-live="polite"`; `:focus-visible`; `prefers-reduced-motion`

## 4. Kiểm thử thật trên trình duyệt

- [x] 4.1 Journey A: tạo tài khoản "Minh" → phim phổ biến + lời mời → chấm 1 phim → "Đang cập nhật…" → applied → gợi ý đổi, lịch sử có phim đó
- [x] 4.2 Journey B (An) và C (Bình): nhãn lý do đúng; Chi không thấy chữ lỗi/fallback nào
- [x] 4.3 Câu chuyện hai tab: tab An + tab Quản trị; admin thêm phim Crime/Drama → chuyển về tab An thấy "Mới" không cần bấm; xoá phim sau khi test
- [x] 4.4 Đo lại checklist UI/UX trên cả hai trang ở 375 px: tràn ngang = 0, kích thước sao, tương phản nút, số vùng `aria-live`, ô nhập có label, có `prefers-reduced-motion`; thao tác bàn phím (Tab tới sao + Enter)
- [x] 4.5 Network log chỉ gọi API cùng origin; tắt Kafka → chấm sao báo "chưa lưu được"; ghi `evidence/p2_demo_user_app.txt` kèm ảnh chụp

## 5. Tài liệu

- [x] 5.1 `docs/TESTING_GUIDE.md`: kịch bản demo hai tab (người dùng / quản trị) và ghi chú persona không phải xác thực
- [x] 5.2 `docs/DEPLOYMENT_DESIGN.md` §Security: `GET /users/{id}/ratings` và `/app` là demo-only; production cần đăng nhập thật và chỉ cho xem lịch sử của chính mình
- [x] 5.3 `docs/SERVING_ARCHITECTURE.md`: hộp USER APP → `/app` (persona) + `/admin`; `README.md` thêm đường dẫn `/app`
