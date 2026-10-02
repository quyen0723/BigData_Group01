## Why

Trang `/demo` hiện là **bảng điều khiển của kỹ sư**: dropdown "Case test", `tier`, `strategy`, `eventId`, `batchId`, `fallbackReason`. Khi demo, giám khảo không thấy được trải nghiệm của **một người dùng thật** — hệ thống cũng chưa có khái niệm tài khoản hay vai trò nào (đăng nhập là non-goal có chủ đích trong `add-demo-web-client`).

Các chức năng đã làm tự chia được theo vai: xem gợi ý, chấm sao, bắt đầu như người mới là việc của **người dùng**; thêm phim mới, xem vòng đời model, soi trạng thái bên trong là việc của **quản trị**. Thiếu đúng một thứ: trang của người dùng. Có nó, buổi demo kể được câu chuyện **hai người** ở hai tab cạnh nhau, và ba journey A/B/C của PRD §4 hiện ra thành trải nghiệm thật.

Review UI/UX qua skill `ui-ux-pro-max` (đo trên trang thật) còn chỉ ra trang hiện tại vỡ bố cục ở màn hẹp, nút sao 21×20 px, chữ trắng trên nút xanh 3.22:1, ô nhập không có label.

M8 là 03/10/2026.

## What Changes

**Trang người dùng `/app` (mới, demo-only)**
- Màn **chọn tài khoản**: 3 persona dựng từ dữ liệu thật (An — user 700008, mới xem vài phim hình sự; Bình — user 1, khán giả lâu năm mê chính kịch/tình cảm, có ALS; Chi — user 127249, thích hài/phiêu lưu/viễn tưởng, không có ALS), nút **Tạo tài khoản mới** (nhập tên → userId mới chưa có lịch sử) và lối vào **Quản trị**.
- **Không mật khẩu, không xác thực**: persona chỉ là cách chọn userId có tên; trang ghi rõ điều này. Persona mô tả bằng gu xem phim, không bịa tuổi/giới tính (PRD §3.2).
- **Feed "Dành cho bạn"**: thẻ phim với lý do bằng lời người dùng (`als` → "Dành riêng cho bạn", `content` → "Giống phim bạn đã thích", `popularity` → "Đang được yêu thích", `new` → "Mới thêm"), chấm 1–5 sao. Không có thuật ngữ kỹ thuật.
- **Phản hồi bất đồng bộ thân thiện**: toast "Đã lưu đánh giá" tự tắt; thẻ hiện "Đang cập nhật gợi ý…" cho tới khi rating được áp dụng; quá hạn chờ thì báo "đánh giá đã lưu, gợi ý sẽ cập nhật sau" — không có chẩn đoán pipeline.
- **Mục "Phim bạn đã đánh giá"** (tối đa 50 phim gần nhất) và trạng thái rỗng cho tài khoản mới (lời mời chấm vài phim — onboarding tối giản cho case 7).
- Tab tự tải lại gợi ý khi được chuyển tới, để phim admin vừa thêm hiện ra ngay ở tab người dùng.
- Phiên đăng nhập lưu **theo tab**; tài khoản tự tạo nhớ trong trình duyệt.

**Trang quản trị `/admin`**
- Là trang `/demo` hiện tại (giữ `/demo` làm đường dẫn phụ). Có lối sang `/app`.
- Sửa lỗi review UI/UX mức CRITICAL/HIGH: bố cục xếp chồng khi màn < 900 px, vùng bấm sao ≥ 40 px, tương phản nút chính ≥ 4.5:1, label cho ô nhập, `aria-live` cho nhật ký, tôn trọng `prefers-reduced-motion`, viền focus rõ.

**API (nhỏ, demo-only)**
- `GET /app`, `GET /admin` (trả file tĩnh).
- `GET /users/{userId}/ratings`: phim đã đánh giá gần nhất (tên, thể loại, số sao).

**Không đổi:** cách chọn tier, fusion, nguồn `new`, `POST /ratings`, streaming, promotion gate, schema Mongo. Không có xác thực phía server; các route demo vẫn chỉ được bảo vệ bằng cờ `api.demo_enabled`.

## Capabilities

### New Capabilities
- `demo-user-app`: trang người dùng `/app` — chọn persona / tạo tài khoản, feed gợi ý bằng lời người dùng, vòng lặp chấm sao với phản hồi bất đồng bộ thân thiện, lịch sử đánh giá, yêu cầu UI/UX (tương phản, vùng bấm, responsive, khả năng tiếp cận, chạy offline).
- `user-rating-history-api`: `GET /users/{userId}/ratings` trả các phim đã đánh giá gần nhất kèm tên và số sao.
- `demo-admin-console`: trang `/admin` (đổi vai trò của `/demo`) và các yêu cầu UI/UX tối thiểu của nó.

### Modified Capabilities
<!-- openspec/specs/ đang trống (3 change trước chưa archive) nên không có delta spec. Quan hệ ghi ở Impact. -->

## Impact

- **Code:** `src/api/static/app.html` (mới); `src/api/static/demo.html` (sửa lỗi UI/UX, thêm lối sang `/app`); `src/api/main.py` (3 route); `src/api/schemas.py`; `src/serving/repository.py` (+ fake) cho lịch sử đánh giá.
- **Quan hệ với change chưa archive:** `/demo` của `add-demo-web-client` và dropdown case của `demo-use-case-scenarios` giữ nguyên, chỉ đổi tên vai thành trang quản trị; non-goal "đăng nhập/xác thực" của `add-demo-web-client` vẫn giữ — persona không phải xác thực.
- **Dependencies:** không thêm gói, không font/CDN ngoài (yêu cầu offline).
- **Bảo mật:** `/users/{userId}/ratings` lộ lịch sử xem phim theo userId như `/debug/users` → chỉ bật khi `api.demo_enabled`; ghi vào `DEPLOYMENT_DESIGN.md` §Security.
- **Thời gian:** khoảng nửa ngày đến một ngày; phần lớn là frontend.
