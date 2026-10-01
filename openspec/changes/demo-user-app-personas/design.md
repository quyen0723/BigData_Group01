## Context

- `/demo` (change `add-demo-web-client`, mở rộng bởi `demo-use-case-scenarios`) là một file HTML tĩnh do API phục vụ. Nó gồm dropdown case test, thẻ kỳ vọng/quan sát, panel hệ thống, form phim demo, nhật ký sự kiện. Thuần cho kỹ sư.
- Hệ thống **không có tài khoản/vai trò**: userId là số ẩn danh của MovieLens. "Đăng nhập/xác thực" là non-goal có chủ đích của `add-demo-web-client`; PRD §3.2 cấm suy diễn nhân khẩu học và loại trừ "Netflix clone".
- Persona dựng từ dữ liệu thật (đo ngày 01/10):

  | Persona | userId | Dữ liệu | Journey PRD §4 |
  |---|---|---|---|
  | An | 700008 | 4 rating, Crime/Drama (Pulp Fiction, Shawshank, Godfather) | B |
  | Bình | 1 | 149 rating, Drama/Romance/Comedy, có ALS | C |
  | Chi | 127249 | 70 rating, Comedy/Drama/Adventure/Sci-Fi, không ALS | C hạ cấp |
  | Tài khoản mới | sinh mới | 0 rating | A |

- Review UI/UX qua skill `ui-ux-pro-max`, đo trên `/demo` ở 375 px:
  - cột gợi ý bị ép còn 32 px, tràn ngang 17 px;
  - nút sao 21×20 px;
  - chữ trắng trên nút `#4f8cff` đạt 3.22:1;
  - 2 ô nhập không có label;
  - 0 vùng `aria-live`, không có `prefers-reduced-motion`;
  - chữ phụ trên thẻ 10–11 px.
- `user_rated` chỉ có index `(userId, movieId)`. Lấy lịch sử theo thời gian sẽ phải sắp xếp trong bộ nhớ (user 1: 149 doc, 19 ms; user nhiều rating sẽ chậm hơn).
- Độ trễ áp dụng rating đo được 12–44 s (`evidence/p2_streaming_latency.txt`).
- M8 = 03/10/2026.

## Goals / Non-Goals

**Goals:**
- Giám khảo dùng được hệ thống **như một người dùng**: chọn tài khoản, xem gợi ý, chấm sao, thấy gợi ý thay đổi — không gặp thuật ngữ kỹ thuật.
- Kể được câu chuyện hai vai (người dùng / quản trị) ở hai tab cạnh nhau.
- Đạt checklist UI/UX của skill trên trang mới; sửa các lỗi CRITICAL/HIGH đã đo trên trang quản trị.

**Non-Goals:**
- Xác thực, mật khẩu, phân quyền phía server, collection `accounts`.
- Tìm kiếm phim, poster, trang chi tiết phim.
- Giải thích "Vì bạn thích *X*" theo từng phim gốc (service không giữ phim seed của từng gợi ý).
- Thay đổi logic gợi ý, streaming hay model.

## Decisions

### D-1. Persona là cấu hình tĩnh phía trang, không phải tài khoản
- 3 persona khai báo trong `app.html`: tên giả, userId thật, mô tả theo gu xem phim. Số rating hiển thị lấy **trực tiếp** từ API (`total`), vì nó tăng sau mỗi lần demo.
- **Đã cân nhắc:**
  - Collection `accounts` phía server: người dùng đã chọn mức "persona, không mật khẩu".
  - Đăng nhập thật: lệch non-goal, tốn 1–1.5 ngày, không thêm bằng chứng Big Data nào.
- Trang ghi rõ "tài khoản demo, không mật khẩu". Nói thẳng điều này khi thuyết trình.

### D-2. Tạo tài khoản = chọn userId mới phía trình duyệt
- Nhập tên (1–40 ký tự) → thử tối đa 5 userId ngẫu nhiên trong dải 500000–599998, chọn cái có `total == 0` từ `GET /users/{id}/ratings`.
- Lưu `{name, userId, createdAt}` vào `localStorage` để lần sau hiện trên màn chọn. Mọi lệnh đọc/ghi bọc `try/catch`: nếu trình duyệt chặn storage, trang vẫn chạy, chỉ không nhớ tài khoản.
- Dùng route lịch sử thay cho `/debug/users`, để trang người dùng không gọi route `debug`.

### D-3. Phiên đăng nhập theo tab (`sessionStorage`)
- Cho phép tab trái là An, tab phải là Quản trị mà không lẫn nhau. Tải lại tab giữ nguyên tài khoản; đóng tab là đăng xuất.
- **Đã cân nhắc:** `localStorage` cho phiên (mọi tab dùng chung một tài khoản) — bị loại vì phá câu chuyện hai tab.

### D-4. Nói bằng lời người dùng
- Nhãn lý do theo thứ tự ưu tiên khi có nhiều nguồn: `als` → "Dành riêng cho bạn", `new` → "Mới thêm", `content` → "Giống phim bạn đã thích", `popularity` → "Đang được yêu thích".
- Ẩn hoàn toàn `tier`, `strategy`, `fallbackReason`, `modelVersion`, điểm số, `eventId`, `batchId`.
- Hệ quả có chủ đích: Chi (fallback) trông y như người dùng bình thường. Đó là "hạ cấp êm" nhìn từ phía người dùng, còn trang quản trị vẫn hiện `fallbackReason`.

### D-5. Phản hồi bất đồng bộ: dung hoà rule toast với độ trễ 12–44 s
- Rule của skill: toast tự tắt sau 3–5 s. Nhưng rating mất tới 44 s mới áp dụng; nếu chỉ có toast thì người xem tưởng bị treo.
- Tách hai lớp:
  1. **Toast** "Đã lưu đánh giá N★", tự tắt sau 4 s.
  2. **Trạng thái trên thẻ** "Đang cập nhật gợi ý…" (thẻ mờ, sao bị khoá), tồn tại tới khi `applied`.
- Khi `applied`: tải lại gợi ý và lịch sử, toast "Gợi ý của bạn đã được cập nhật".
- Quá `rating_poll_timeout_seconds`: thẻ ghi "Đánh giá đã lưu, gợi ý sẽ cập nhật sau". Câu này **đúng sự thật**: 202 nghĩa là Kafka đã nhận bền vững. Không nhắc pipeline hay Kafka; chẩn đoán chỉ có ở trang quản trị.
- Lỗi 4xx/503: "Chưa lưu được đánh giá, vui lòng thử lại", mở khoá thẻ.

### D-6. Lịch sử đánh giá lấy từ `user_history.recent_movieIds`
- `recent_movieIds` đã được streaming giữ sẵn: sắp mới nhất trước, giới hạn 50 (`recent_cap`). Route đọc danh sách này, lấy số sao bằng một truy vấn `$in` trên `user_rated` (dùng index `(userId, movieId)`), lấy tên/thể loại từ `movies`.
- **Đã cân nhắc:** `user_rated.find({userId}).sort({ratingTs:-1})` — phải sắp trong bộ nhớ trên toàn bộ rating của user (không giới hạn với user nhiều rating), hoặc phải thêm index mới trên collection 32 triệu doc. Bị loại.
- Lợi ích phụ: lịch sử hiển thị chính là lịch sử router dùng để chọn seed, nên "Phim bạn đã đánh giá" và "Giống phim bạn đã thích" luôn nhất quán.
- Phim không còn trong `movies` (phim demo đã xoá) vẫn được liệt kê với `inCatalog: false`, để lịch sử không nói dối.

### D-7. Tự tải lại khi tab được chuyển tới
- Lắng nghe `visibilitychange`: khi tab hiện lại thì tải lại gợi ý. Đủ cho câu chuyện "admin thêm phim → chuyển tab → thấy MỚI".
- **Đã cân nhắc:** poll định kỳ — tốn request vô ích, và làm danh sách nhảy khi người xem đang đọc.

### D-8. Hệ thống thị giác cho `/app` (từ skill, đã lọc)

| Thành phần | Chọn | Đo |
|---|---|---|
| Phong cách | Dark Mode tối giản (skill: style "Dark Mode (OLED)", product "Media Platform") | — |
| Nền / bề mặt | `#000000` / `#0F0F23` (skill: color "Video Streaming/OTT") | — |
| Nút chính | đỏ điện ảnh `#E11D48`, chữ trắng | 4.70:1 |
| Chữ / chữ phụ | `#F8FAFC` / `#94A3B8` | 20.07:1 / 7.36:1 |
| Font | font hệ thống (Segoe UI, -apple-system, Roboto) | — |
| Icon | SVG nội tuyến (sao, dấu tích, đăng xuất) | — |
| Cỡ chữ | thân 16 px, phụ ≥ 13 px | — |

- **Bị loại từ đề xuất tự động của skill:** pattern "App Store Style Landing" (trang quảng bá có nút tải app, không phải feed trong app) và font Righteous/Poppins (tải từ Google Fonts, vi phạm yêu cầu offline).
- **Sao 40×40 px thay vì 44:** 5 sao × 40 px + khoảng cách 4 px vừa thẻ 220 px trên laptop; dưới 600 px lưới về 1 cột nên sao lên 44 px.
- Skeleton 10 thẻ khi tải (API 60–370 ms, vượt ngưỡng 300 ms của skill); toast trong vùng `aria-live="polite"`; viền focus `:focus-visible` 2 px; `prefers-reduced-motion` tắt mọi chuyển động.

### D-9. Trang quản trị = `/demo` hiện tại, thêm route `/admin`
- Hai route cùng trả `demo.html`, giữ `/demo` cho tài liệu và evidence cũ. Đổi tiêu đề thành "Quản trị", thêm lối sang `/app`.
- Nút chính đổi từ `#4f8cff` (3.22:1) sang `#2563EB` (5.17:1). Giữ màu xanh để phân biệt bằng mắt với trang người dùng màu đỏ.
- Dưới 900 px, panel phải xếp xuống dưới cột chính (`flex-wrap`/media query).
- Thêm label cho `userIdInput`/`movieTitle`, `aria-live` cho nhật ký, `aria-label` cho sao, `prefers-reduced-motion`, `:focus-visible`.

### D-10. Bảo mật
- Không có xác thực. Persona không phải cơ chế bảo mật: ai biết URL đều gọi được mọi route demo.
- `GET /users/{userId}/ratings` lộ lịch sử xem phim theo userId, cùng loại với `/debug/users`, nên chỉ bật khi `api.demo_enabled` và được ghi vào `DEPLOYMENT_DESIGN.md` §Security.
- Ở production, phần này thay bằng đăng nhập thật và chỉ cho xem lịch sử của chính mình (design-only).

## Risks / Trade-offs

- **[Persona bị "tiêu hao": An rate nhiều lần trong lúc demo sẽ vượt T=10, chuyển sang `enough_history`]** → Mô tả persona theo gu chứ không theo số; số rating hiển thị trực tiếp. Có thể seed lại user khác bằng `scripts/seed_demo_users.py --user-id`.
- **[Giám khảo hiểu nhầm persona là đăng nhập thật]** → Ghi rõ trên màn chọn, và nói khi thuyết trình.
- **[Độ trễ 12–44 s lộ rõ hơn trong giao diện người dùng]** → Trạng thái "Đang cập nhật gợi ý…" nằm ngay trên thẻ (D-5). Trong kịch bản demo, chấm sao trước rồi kể chuyện trong lúc chờ.
- **[Tài khoản mới trùng userId test cũ có lịch sử]** → Kiểm tra `total == 0`, tối đa 5 lần.
- **[Trình duyệt chặn `localStorage`/`sessionStorage`]** → Mọi truy cập storage bọc `try/catch`; trang vẫn dùng được, chỉ không nhớ tài khoản/phiên.
- **[Hai trang HTML lặp code (gọi API, poll)]** → Chấp nhận cho demo (mỗi trang tự đủ, không build tooling). Phần lặp nhỏ (`fetchJson`, poll).
- **[Hết giờ trước M8]** → Thứ tự: route lịch sử → `/app` (chọn persona + feed + chấm sao) → lịch sử + tạo tài khoản → sửa `/admin`. Mỗi lớp xong là dùng được.

## Migration Plan

1. Thêm route và repository, restart `api` (code được mount, không cần build).
2. Thêm `app.html`, sửa `demo.html` (file tĩnh, tải lại trình duyệt là thấy).
3. Rollback: xoá route `/app`, `/admin`, `/users/{id}/ratings`; khôi phục `demo.html`. Không có thay đổi dữ liệu.

## Open Questions

- Tên persona An/Bình/Chi là tạm; nhóm có muốn tên khác không?
- Có cần nút "Đặt lại" để xoá các tài khoản tự tạo khỏi trình duyệt không?
