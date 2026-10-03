## 1. Chuẩn bị

- [x] 1.1 Tạo nhánh `feat/rebuild-ui-react` từ `main` mới nhất; chạy pytest làm mốc (kỳ vọng 164 pass)
- [x] 1.2 Tạo `evidence/p2_ui_react.txt`; liệt kê **danh sách đối chiếu chức năng** của hai trang cũ (mọi khối, nút, trạng thái, thông báo của `app.html` và `demo.html`) để task 8.1/8.2 tick từng dòng

## 2. Backend nhỏ và cách phục vụ

- [x] 2.1 `DemoSettingsOut.tierThreshold` lấy từ `routing.T_few_enough`; pytest: trường có mặt, các trường cũ không đổi
- [x] 2.2 Cờ `api.ui` (`legacy` | `react`, mặc định `legacy`) trong `configs/serving.yaml` và `ServingConfig`; biến môi trường `WEB_DIST_DIR` (mặc định `/app/web-dist`)
- [x] 2.3 Route `GET /app-next`, `/admin-next` (404 khi demo tắt hoặc chưa build); `/legacy/app`, `/legacy/admin` (trang cũ, 404 khi demo tắt); `/app`, `/admin`, `/demo` chọn theo `api.ui`, thiếu bản build thì quay về trang cũ và ghi cảnh báo
- [x] 2.4 Phục vụ `/ui/assets/*` từ `dist/assets/` bằng một route (không dùng StaticFiles vì thư mục build có thể chưa có); 404 cho mọi `/ui/*` khi demo tắt và cho đường dẫn thoát khỏi `assets/`
- [x] 2.5 pytest với thư mục build giả tạm thời: mọi scenario trong `specs/web-frontend` về route, cờ, rollback, assets; các test cũ của `/app`, `/admin`, `/demo` vẫn pass khi `api.ui = legacy`
- [x] 2.6 `.dockerignore` mới (`movielens32m/`, `*.zip`, `.venv*`, `web/node_modules`, `web/dist`, `.omc/`, `.claude/`, `logs/`, `.git/`); `.gitignore` thêm `web/node_modules`, `web/dist`

## 3. Khung frontend

- [x] 3.1 Dựng `web/` (Vite + React 19 + TypeScript strict), hai entry `app.html`/`admin.html`, `base: "/ui/"`, dev proxy sang `127.0.0.1:8088` cho các đường dẫn API
- [x] 3.2 Tailwind v4 + shadcn/ui: khai báo token D-8 trong theme; chép các component cần dùng (button, card, badge, input, label, dialog, alert-dialog, sidebar, sheet, table, skeleton, tooltip, select/checkbox, progress, sonner)
- [x] 3.3 Font `@fontsource` Fira Sans (400/500/600) và Fira Code (400/500). **Kiểm dấu tiếng Việt** trên chuỗi mẫu; thiếu thì chuyển sang font hệ thống và ghi lại quyết định
- [x] 3.4 `npm run gen:api` (openapi-typescript từ `/openapi.json`) và commit `schema.d.ts`; TanStack Query provider, lucide-react, Vitest + Testing Library
- [x] 3.5 Script kiểm: kích thước gzip của từng trang so với ngân sách; tìm URL ngoài trong bản build; tương phản cho mọi cặp token và ô thể loại

## 4. Phần dùng chung

- [x] 4.1 API client trả `{ ok, status, body }` (lỗi mạng → `status: 0`) và query keys
- [x] 4.2 Hook theo D-3: `useRecommendations`, `useRatingHistory`, `useDebugUser`, `useSystemStatus` (poll 10 s chỉ khi mục đang mở), `useRatingFlow` bọc lớp `RatingFlow` (POST rồi poll 1 s, dừng khi `applied` hoặc hết `ratingPollTimeoutSeconds`; tách khỏi thẻ để khoá sao sống qua lần tải lại) và `lib/retry.ts` cho id thử lại
- [x] 4.3 `lib/genre.ts` (19 thể loại + `(no genres listed)` → họ màu, icon lucide đã kiểm tên), `lib/movie.ts` (tách năm), `lib/sources.ts` (nguồn chính, chia hàng theo D-5)
- [x] 4.4 Component `GenreTile`, `StarRating` (`role="radiogroup"`, phím mũi tên, vùng bấm 40/44 px, `aria-label`), `MovieCard` (hạng `#n`, nhãn lý do, huy hiệu "Mới", trạng thái chờ)
- [x] 4.5 Vitest: chia hàng (hai nguồn, một nguồn, nhãn ghép `als+content`), tách năm (có/không), đủ ánh xạ thể loại, `useRetryEventId` (thử lại sau 503, đổi số sao rồi 202 thì xoá mọi id của phim, đăng xuất xoá hết)

## 5. Trang user

- [x] 5.1 Kho tài khoản (sessionStorage theo tab, localStorage cho tài khoản đã tạo, bọc try/catch) + Context; màn chọn tài khoản với An/Bình/Chi và dòng "tài khoản demo, không mật khẩu"
- [x] 5.2 Tạo tài khoản: label, kiểm tra 1–40 ký tự khi rời ô, lỗi `role=alert`, chọn `userId` trống (≤ 5 lần), nút khoá khi đang chạy
- [x] 5.3 `TierBanner` đủ mọi dòng của bảng D-5, ngưỡng từ `tierThreshold`, `aria-live="polite"`
- [x] 5.4 Feed: skeleton, hàng theo nguồn hoặc lưới; chấm sao với khoá thẻ, toast success/error, nút thử lại dùng lại `eventId`, thông báo hết hạn chờ; tải lại khi focus mà không mở khoá thẻ đang chờ
- [x] 5.5 Mục "Phim bạn đã đánh giá" (50 phim, tổng số) và trạng thái rỗng; link "bỏ qua tới nội dung chính"; đăng xuất
- [x] 5.6 Vitest: banner cho từng trường hợp; thẻ đang chờ vẫn khoá khi feed tải lại; kho tài khoản khi storage ném lỗi

## 6. Trang admin

- [x] 6.1 Khung sidebar shadcn (thành ngăn kéo dưới 1024 px), hook điều hướng theo hash, header có version model và link sang trang user; hash lạ → Tổng quan
- [x] 6.2 Tổng quan: thẻ KPI (model, số version, tiến độ retrain, số phim demo, trạng thái API)
- [x] 6.3 Case test: chép **nguyên văn** 12 case từ `demo.html` sang `admin/cases.ts`; thẻ kỳ vọng/quan sát; lưới gợi ý có chấm sao
- [x] 6.4 Người dùng `#/users/<id>`: ô nhập và lối tắt persona, gợi ý hiện tại, trạng thái bên trong (tier, interaction_count, recent/positive, pipeline)
- [x] 6.5 Phim: danh sách phim demo; dialog thêm phim (tên, chọn thể loại, kiểm tra khi rời ô, lỗi `role=alert`); xoá qua dialog xác nhận
- [x] 6.6 Model: bảng version, gate checks hiện icon + chữ PASS/FAIL, tiến độ retrain
- [x] 6.7 Nhật ký: các thao tác trong phiên có giờ, lưu sessionStorage
- [x] 6.8 Vitest: điều hướng hash (reload giữ mục, hash lạ), dialog xoá chỉ gọi API sau khi xác nhận, form thêm phim không gửi khi thiếu tên

## 7. Docker

- [x] 7.1 `docker/api.Dockerfile`: stage `node:22-alpine` chạy `npm ci` + `npm run build`; stage cuối `COPY --from` vào `/app/web-dist`; Node không có trong image cuối
- [x] 7.2 Build lại image `api` và chạy: `/app-next`, `/admin-next` trả bản mới; tắt demo thì chúng, `/legacy/*` và `/ui/assets/*` trả 404; bật lại demo. Ghi kích thước image trước và sau vào evidence

## 8. Kiểm chứng (D-12)

- [x] 8.1 Trang user trên trình duyệt (bản build trong Docker): tick hết danh sách đối chiếu ở 1.2; hành trình tạo tài khoản → chấm phim → applied → gợi ý đổi; persona An, Bình (thấy hai hàng), Chi (banner fallback)
- [x] 8.2 Trang admin trên trình duyệt: tick hết danh sách đối chiếu; chạy cả 12 case; thêm và xoá một phim demo (dọn dẹp sau đó)
- [x] 8.3 Bàn phím đi hết hai trang; 375 / 768 / 1024 / 1440 px không tràn ngang; `prefers-reduced-motion` (đã đo: responsive 4 độ rộng, mũi tên/Home/End trên nhóm sao, tên cho mọi điều khiển. **Chưa kiểm được trên pane:** nhấn Tab thật, viền focus nhìn thấy và `prefers-reduced-motion`, vì cửa sổ không hoạt động; xem evidence mục 3)
- [x] 8.4 Script: tương phản đạt, không URL ngoài, kích thước gzip trong ngân sách; số đo ghi vào evidence
- [x] 8.5 Toàn bộ pytest và Vitest pass; không có test bị skip hay để trống (pytest 184, Vitest 162 / 21 file, không có skip/only/todo; xem evidence mục 4)
- [x] 8.6 Review độc lập (agent code-reviewer, chỉ đọc) và xử lý các điểm cần sửa (8 điểm + nit đã sửa, thêm test hồi quy kiểm bằng đột biến; xem evidence mục 4)

## 9. Chuyển đổi và tài liệu

- [x] 9.1 Khi 8.x đạt hết: đặt `api.ui: react` trong `configs/serving.yaml`; kiểm `/app`, `/admin`, `/demo` trả bản mới và `/legacy/*` trả trang cũ; thử rollback về `legacy` rồi đặt lại `react` (đã đo trên stack thật, xem evidence mục 5; test pytest của cờ cập nhật: file cấu hình = react, thiếu khoá = legacy)
- [x] 9.2 README: cách chạy dev (`npm run dev`), build, cờ `api.ui`; `docs/TESTING_GUIDE.md` mục 2b: đường dẫn mới, `/legacy`, checklist (README.md, `web/README.md` mới, TESTING_GUIDE mục "Giao diện React")
- [x] 9.3 Hoàn thiện `evidence/p2_ui_react.txt`; `openspec validate rebuild-ui-react --strict` pass; commit và push chỉ khi người dùng yêu cầu (evidence mục 1–5 đủ; chưa commit, chờ người dùng yêu cầu)
