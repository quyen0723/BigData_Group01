## Why

Hai trang demo hiện tại (`src/api/static/app.html` 584 dòng, `demo.html` 694 dòng) là HTML và JavaScript viết tay: dựng DOM bằng `el()`, tự viết polling, tự bắt `visibilitychange`. Chúng chạy đúng và đã qua review UI/UX, nhưng trông cũ, khó đọc, và mỗi tính năng mới đều tốn công. Change kế tiếp (`admin-recommendation-explainer`) sẽ thêm ba mục admin có bảng, biểu đồ và bộ lọc. Viết thêm chúng theo kiểu cũ sẽ còn tốn hơn.

Buổi explore đã chốt hướng: React + Vite, hai trang tách biệt (admin và user), Tailwind + shadcn/ui. Design system đã lọc qua skill `ui-ux-pro-max` với ràng buộc của dự án: chạy offline, tương phản AA, một phong cách cho cả hai trang. Đo trên dữ liệu thật cho thấy phần lớn user chỉ nhận gợi ý từ một nguồn (user mới: popularity 10/10; Minh, An, Chi: content 10/10; chỉ Bình có ALS 3 + content 7). Vì vậy trang user cần thêm cách kể câu chuyện "hệ thống lai" ngoài việc chia hàng theo nguồn.

## What Changes

**Frontend mới `web/`**
- React + Vite + TypeScript, chế độ **multi-page**: hai file HTML vào, hai bundle ra. Admin và user tách biệt; user không tải code admin. Hai trang dùng chung API client, kiểu dữ liệu và component.
- Tailwind CSS + shadcn/ui, TanStack Query (cache, polling, tải lại khi tab được focus), lucide-react, font Fira Sans + Fira Code **tự đóng gói** (`@fontsource`, không Google Fonts). Kiểu dữ liệu API sinh từ `/openapi.json` của FastAPI.
- **Design system dùng chung**: nền `#F8FAFC`, chữ `#0F172A`, chữ phụ `#475569`, màu chính `#2563EB` (hover `#1E40AF`), nhấn `#FBBF24` luôn đi với chữ tối; chuyển động 150–300 ms; thang lớp xếp chồng cố định. Mọi cặp màu chữ/nền đạt ≥ 4.5:1.

**Trang user (đủ chức năng như hiện tại, và thêm)**
- Giữ nguyên: chọn persona An/Bình/Chi, tạo tài khoản (sessionStorage theo tab, localStorage cho tài khoản đã tạo), feed có nhãn lý do bằng lời người dùng và huy hiệu "Mới", chấm sao với phản hồi bất đồng bộ (toast, trạng thái đang cập nhật, poll tối đa `rating_poll_timeout_seconds`, giữ `eventId` khi thử lại), lịch sử đánh giá, tải lại khi quay về tab.
- Mới: **banner giải thích theo tier** (đã chấm bao nhiêu phim, đang dùng nguồn nào, còn bao nhiêu phim nữa thì đổi tier); **chia hàng theo nguồn** khi gợi ý đến từ ít nhất hai nguồn, chỉ một nguồn thì hiện lưới; **thẻ phim có ô màu và icon theo thể loại chính**, năm phát hành tách từ tên phim.

**Trang admin (đủ chức năng như hiện tại, bố cục mới)**
- Khung **sidebar** (shadcn `Sidebar`, thu thành ngăn kéo trên màn hẹp) với các mục: Tổng quan · Case test · Người dùng · Phim · Model & retrain · Nhật ký. Mỗi mục là một màn hình, chuyển bằng URL hash nên tải lại trang vẫn đúng mục.
- Chuyển toàn bộ chức năng hiện có sang: 12 case test (thẻ kỳ vọng/quan sát), lưới gợi ý có chấm sao, trạng thái bên trong của user, thêm/xoá phim demo (xoá phải xác nhận), vòng đời model và gate checks, tiến độ retrain, nhật ký sự kiện.
- Chừa chỗ trong sidebar cho mục Thể loại và khung giải thích của change sau, nhưng **không** làm chúng ở đây.

**Phục vụ và chuyển đổi**
- FastAPI phục vụ bản build ở **`/app-next`** và **`/admin-next`** trước, vẫn chặn 404 khi `api.demo_enabled` tắt. Trang cũ giữ nguyên ở `/app`, `/admin`, `/demo`.
- Bước chuyển nằm trong change này nhưng chỉ làm khi bản mới qua checklist: `/app` và `/admin` trả bản mới, trang cũ lùi về `/legacy/app` và `/legacy/admin` làm dự phòng. Không có bản build thì các route tự dùng trang cũ, để test và máy chưa build vẫn chạy.
- `docker/api.Dockerfile` thêm stage `node:22` để build `web/`. Bản build đặt ngoài thư mục `src` mà container mount đè, nên ai chạy `docker compose up --build` cũng có giao diện mới mà không cần cài Node.

**API:** chỉ thêm một trường `tierThreshold` vào khối `demo` của `GET /debug/system` (route demo-only, chỉ thêm chứ không đổi trường cũ), vì banner cần ngưỡng T mà API chưa trả. Mọi endpoint khác, logic gợi ý, streaming, Mongo, cờ `api.demo_enabled` và cách nó chặn route giữ nguyên. Không thêm xác thực.

**Ngoài phạm vi (change sau):** khung giải thích gợi ý, tìm/lọc danh mục phim, thống kê thể loại, điểm trung bình/WR cho từng phim, sửa tie-break `support=0`, cách chọn phim mới theo thể loại (hướng A + C). Cũng không làm poster (cần Internet), chế độ tối, hay đổi đường dẫn API.

## Capabilities

### New Capabilities
- `web-frontend`: project `web/` (Vite multi-page), cách build (dev proxy, Docker multi-stage), cách FastAPI phục vụ bản build (route `-next`, bước chuyển, `/legacy`, tự quay về trang cũ khi chưa build), yêu cầu offline và chặn bằng `demo_enabled`.
- `ui-design-system`: token màu, font tự đóng gói, ngưỡng tương phản, focus, vùng bấm, chuyển động, trạng thái tải/lỗi, quy tắc cho bảng và biểu đồ; áp dụng cho cả hai trang.

### Modified Capabilities
<!-- openspec/specs/ đang trống (các change trước chưa archive) nên delta viết dạng ADDED trong thư mục cùng tên. Archive sau `demo-user-app-personas`. -->
- `demo-user-app`: trang user dựng lại bằng React với đủ chức năng cũ, thêm banner theo tier, chia hàng theo nguồn, thẻ có ô màu thể loại.
- `demo-admin-console`: admin có khung sidebar và các mục; mọi chức năng cũ (case test, phim demo, model, retrain, nhật ký) chuyển sang.

## Impact

- **Code mới:** `web/` (package.json, lockfile, cấu hình Vite/Tailwind/TypeScript, mã nguồn, test Vitest).
- **Code sửa:** `src/api/main.py` (route `/app-next`, `/admin-next`, `/legacy/*`, phục vụ assets của bản build, tự quay về trang cũ, cờ chọn giao diện); `src/api/schemas.py` (`tierThreshold`); `configs/serving.yaml` (`api.ui`); `docker/api.Dockerfile` (stage node); `.dockerignore` mới (repo chưa có, build context hiện gồm cả `movielens32m/` 1.7 GB); `.gitignore` (`web/node_modules`, `web/dist`); test pytest cho route và cách chặn.
- **Docs:** README (cách chạy dev, build), `docs/TESTING_GUIDE.md` mục 2b (đường dẫn mới, checklist chuyển đổi).
- **Phụ thuộc:** Node 22 để build (trong Docker; ở máy dev chỉ cần khi sửa giao diện). Thư viện frontend được khoá phiên bản trong lockfile.
- **Rủi ro:** thêm một toolchain vào dự án Python; kích thước image `api` tăng do stage build (stage node không vào image cuối). Bản mới phải đạt checklist trước khi thay trang cũ.
- **Thời gian:** khoảng 2,5–3 ngày. Đổi dần nên không ảnh hưởng buổi demo: trang cũ luôn còn.
