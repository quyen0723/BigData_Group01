## Context

- Collection `movies` (87,585 tài liệu): `_id` = movieId, `title`, `genres` ("Crime|Drama"), `support` (số rating lúc nạp), và phim demo (`_id` từ 9,000,000) có thêm `addedAt`.
- Số liệu điểm TB chỉ có ở `movie_stats` (36,526 phim, rating trước cutoff 2016-10-13) cộng ledger. `LivePopularity` đã giữ baseline trong bộ nhớ và cache kết quả quét ledger (TTL 2 giây).
- Admin hiện chỉ có `DemoMovies` (thêm/xoá). Trang user có `Feed` (gợi ý) và `RatingFlow` (chấm sao, khoá sao, toast).

## Goals / Non-Goals

**Goals:** tìm và xem mọi phim trong admin; tìm và chấm bất kỳ phim nào trên trang user; số liệu khớp nguồn WR; không chậm đáng kể; không đổi hành vi gợi ý.

**Non-Goals:** tìm toàn văn, gợi ý tên khi gõ, tìm theo diễn viên, thống kê thể loại, giải thích gợi ý, xác thực.

## Decisions

### D-1. Danh mục nằm trong bộ nhớ, lọc và sắp xếp bằng Python
Sắp theo điểm TB hoặc WR cần số liệu từ baseline cộng ledger, không có trong `movies`, nên không đẩy được xuống Mongo. 87 nghìn dòng (id, tên, tên viết thường, thể loại, support) khoảng vài chục MB, lọc và sắp xếp cỡ chục đến vài chục mili giây. `src/serving/catalog.py` thuần (không I/O) có `search(entries, stats, ...)`; repository có `get_catalog()` đọc `movies` một lần; một `CatalogCache` sắp xếp danh mục theo movieId một lần và giữ nó; hết 30 giây thì request nhận **bản cũ ngay** và một luồng nền đọc lại (không request nào chờ lần đọc 87 nghìn dòng, khoảng 2 giây); thêm hoặc xoá phim demo qua API này thì bỏ bản cũ để request kế tiếp đọc lại và thấy thay đổi. Sửa `movies` bằng tay trong Mongo hiện sau tối đa khoảng 30 giây.

### D-2. Tìm kiếm
Tách `q` theo khoảng trắng, mỗi từ (viết thường) phải là chuỗi con của tên viết thường. Không bỏ dấu, không mờ. Gõ "pulp" ra Pulp Fiction (1994); gõ "1994" ra các phim năm 1994 (năm nằm trong tên). `q` rỗng nghĩa là không lọc theo tên. `genre` là một trong 19 thể loại của `MOVIELENS_GENRES` (không phân biệt hoa thường), sai thì 422.

### D-3. Số liệu mỗi dòng
- `ratings` = `support` + số rating mới đếm từ ledger (phim demo: `support` 0).
- `trainRatings` (n0), `newRatings`, `avgRating` (R) và `wr` chỉ có khi phim có rating trong baseline hoặc ledger; ngược lại `null`. WR dùng `m` và `C` của cấu hình `popularity` và baseline.
- Số liệu lấy từ một ảnh chụp do `LivePopularity.snapshot()` trả (baseline + deltas, dùng chung cache, không bao giờ ném lỗi, `None` khi thiếu baseline). Khi `None`: `hasStats = false`, điểm TB và WR là `null`, sắp theo `avg` hoặc `wr` bị từ chối bằng 422 kèm lý do rõ.
- Phim ra sau cutoff nên `ratings` lớn nhưng `avgRating` null: giao diện ghi "chưa có số liệu" (không phải 0).

### D-4. Hợp đồng `GET /movies`
Tham số: `q` (0–100 ký tự), `genre`, `sort` ∈ `title` | `ratings` | `avg` | `wr` (mặc định `ratings`), `order` ∈ `asc` | `desc` (mặc định `desc`, riêng `title` mặc định `asc` khi không truyền), `page` ≥ 1, `size` 1–50 (mặc định 20). Thứ tự ổn định: khoá chính rồi `movieId` tăng. Phim không có giá trị ở khoá sắp (avg, wr) luôn nằm cuối, cả hai chiều. Trả `{total, page, size, pages, hasStats, m, c, items[]}`, mỗi phần tử `{movieId, title, genres[], ratings, trainRatings, newRatings, avgRating, wr, isDemo}`. Trang vượt quá thì trả danh sách rỗng với `total` đúng. Chặn bằng `require_demo` trước khi kiểm tham số (404 kể cả tham số sai).

### D-5. Admin: bảng Danh mục phim
Trong mục `#/movies`, bên dưới phần phim demo. Ô tìm (đợi 300 ms sau khi ngừng gõ), chọn thể loại, chọn "Sắp xếp theo" và nút đảo chiều, phân trang (Trước/Sau, "Trang 3/120", tổng số phim). Cột: Phim (tên và thể loại), Số rating (kèm "+n mới"), Điểm TB, WR (4 chữ số), nhãn "demo" cho phim demo. Giá trị thiếu hiện "—" với `title` giải thích. Trạng thái: đang tải (khung), lỗi có nút Thử lại, rỗng ("Không có phim nào khớp"). Chuyển trang giữ cuộn đầu bảng, giữ dữ liệu cũ khi tải trang mới.

### D-6. Trang user: ô Tìm phim
Một mục "Tìm phim để chấm" ngay dưới banner, trên "Dành cho bạn". Ô tìm và chọn thể loại; chỉ gọi API khi đã gõ ít nhất 2 ký tự hoặc chọn thể loại; hiện 12 kết quả mỗi lần với nút "Xem thêm". Mỗi kết quả là `MovieCard` (thêm tuỳ chọn ẩn hạng) với hàng sao, chấm qua đúng `RatingFlow` của trang (cùng khoá sao, toast, làm mới gợi ý và lịch sử). Phim có trong lịch sử gần đây (50 phim mới nhất) hiện "Bạn đã chấm N sao" và vẫn chấm lại được; chấm lại một phim đã chấm không làm tăng số rating của user (streaming ghi theo cặp user-phim) và WR chỉ đếm bản mới nhất. Trang user không hiện điểm TB hay WR (không từ kỹ thuật).

### D-7. Kiểm chứng
Thuần: lọc, sắp xếp (kể cả giá trị thiếu), phân trang, tách từ khoá. API: gate, tham số, 422, không có baseline, phim demo, làm mới sau khi thêm/xoá. Giao diện: gõ rồi mới gọi, lọc thể loại, phân trang, chấm từ kết quả đi qua `RatingFlow`. Thật: đếm kết quả trên Mongo (ví dụ "pulp", thể loại Western, sắp theo số rating) và đo thời gian.

## Risks / Trade-offs

- **[Bộ nhớ và thời gian]** vài chục MB và vài chục ms mỗi lần tìm: chỉ route demo; đo ở task 8.
- **[Điểm TB lệch so với số rating]** vì baseline là tập train: nói rõ trong giao diện và tài liệu.
- **[Rating thật từ ô tìm]** vào Mongo và ledger như mọi rating trên trang; tài khoản tạo trên trang nằm ngoài dải user giả nên script dọn không xoá được (đã biết, ghi trong tài liệu).

## Migration Plan

Thêm route và giao diện; không đổi dữ liệu. Rollback: bỏ route (hoặc tắt demo). Không cần chạy loader.

## Open Questions

- Có cần tìm theo `movieId`? Đề xuất: không (gõ số vào ô tìm chỉ khớp tên).
