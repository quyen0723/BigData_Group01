## Why

Hai thiếu sót khiến không tự test được hệ thống qua giao diện:

1. **Admin không thấy danh mục phim.** Mục "Phim" chỉ liệt kê phim demo do người dùng tự thêm (đang trống: "Chưa có phim demo nào"), trong khi Mongo có **87,585 phim** của MovieLens. API chỉ có `POST /movies` và `DELETE /movies/{id}`, không có API nào đọc danh sách.
2. **Không có ô tìm kiếm ở đâu cả.** Trang user chỉ cho chấm các phim hệ thống đã gợi ý, nên không chọn được phim theo ý mình. Muốn kiểm các case như "user thích Western thì gợi ý đổi ra sao", "chấm đúng phim X rồi xem phim giống X", "phim mới khớp thể loại" thì phải tìm và chấm đúng một phim cụ thể.

Phần này vốn nằm trong dự kiến của change `admin-recommendation-explainer` (`GET /movies?q=&genre=&sort=`) nhưng chưa làm. Change này tách riêng đúng phần cần để test, nhỏ và độc lập.

## What Changes

**API (demo-only, 404 khi `api.demo_enabled` tắt)**
- `GET /movies?q=&genre=&sort=&order=&page=&size=`: tìm theo tên (không phân biệt hoa thường, mọi từ khoá đều phải có mặt), lọc một thể loại, sắp theo tên, số rating, điểm trung bình hoặc WR, phân trang. Mỗi dòng: `movieId`, `title`, `genres`, số rating (toàn bộ + mới), điểm TB và WR khi có số liệu, cờ `isDemo`.
- Số liệu lấy từ cùng nguồn với danh sách phổ biến (baseline tập train cộng rating mới trong ledger), dùng chung cache của `LivePopularity`. Thiếu baseline thì vẫn tìm và sắp theo tên và số rating, chỉ không có điểm TB và WR.
- Danh mục đọc từ collection `movies` vào bộ nhớ (khoảng 87 nghìn dòng) và giữ 30 giây; thêm hoặc xoá phim demo thì làm mới ngay.

**Admin**
- Mục **Phim** thêm bảng **Danh mục phim**: ô tìm, bộ lọc thể loại, chọn cách sắp xếp, phân trang, cột số rating, điểm TB, WR, nhãn "demo". Phần thêm/xoá phim demo giữ nguyên, nằm phía trên.

**Trang user**
- Ô **Tìm phim** (kèm lọc thể loại): kết quả là các thẻ phim có hàng sao, chấm bằng đúng luồng hiện có (khoá sao, toast, cập nhật gợi ý). Phim bạn đã chấm hiện "Bạn đã chấm N sao" nhưng vẫn chấm lại được.

**Giữ nguyên:** thuật toán gợi ý, streaming, Mongo, ledger, WR, mọi API khác. Không thêm xác thực (vẫn chỉ route demo).

**Ngoài phạm vi:** giải thích vì sao gợi ý phim này, thống kê theo thể loại, đổi quy tắc chọn phim mới (vẫn thuộc `admin-recommendation-explainer`).

## Capabilities

### New Capabilities
- `movie-catalog`: API đọc và tìm phim, số liệu kèm theo, sắp xếp, phân trang, bộ nhớ đệm.
- `catalog-ui`: bảng danh mục trong admin và ô tìm phim để chấm trên trang user.

### Modified Capabilities
<!-- openspec/specs/ đang trống (các change trước chưa archive) nên delta viết dạng ADDED. Liên quan: demo-admin-console, demo-user-app. Archive sau live-weighted-popularity. -->

## Impact

- **Code mới:** `src/serving/catalog.py` (thuần), route `GET /movies` và schema, `web/src/admin/Catalog.tsx`, `web/src/user/MovieSearch.tsx` (+ hook, test).
- **Code sửa:** `src/serving/repository.py` (`get_catalog`), `src/serving/live_popularity.py` (một hàm lấy toàn bộ số liệu), `src/api/main.py` và `schemas.py`, `web/src/admin/DemoMovies` (đặt cạnh bảng), `web/src/user/Home.tsx`, `web/src/shared/ui/movie-card.tsx` (ẩn hạng, dòng "đã chấm"), `docs/TESTING_GUIDE.md`.
- **Rủi ro:** (1) số liệu điểm TB lấy từ **tập train** (đến 10/2016) cộng rating mới, nên phim ra sau đó có số rating nhưng chưa có điểm TB: giao diện nói rõ "chưa có số liệu"; (2) bộ nhớ thêm khoảng vài chục MB cho danh mục; (3) rating chấm từ ô tìm là dữ liệu thật trong Mongo, như mọi rating trên trang.
- **Thời gian:** khoảng 1 ngày.
