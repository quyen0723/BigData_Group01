## Context

- Hai trang hiện tại là file tĩnh do FastAPI trả bằng `FileResponse`: `/app` → `static/app.html` (584 dòng), `/admin` và `/demo` → `static/demo.html` (694 dòng). Cả hai trả 404 khi `api.demo_enabled` tắt; các route JSON demo-only dùng dependency `require_demo` (chặn trước khi validate body).
- Endpoint mà hai trang gọi: `GET /recommendations/{id}`, `POST /ratings`, `GET /ratings/{eventId}`, `GET /users/{id}/ratings`, `GET /debug/users/{id}`, `GET /debug/system`, `POST /movies`, `DELETE /movies/{id}`. FastAPI có sẵn `/openapi.json`. Chưa bật CORS.
- Dữ liệu thật về nguồn gợi ý (10 gợi ý mỗi user): user mới popularity 10; Minh và An content 10 (few_history); Chi content 10 (enough_history, không có ALS, `fallbackReason = als_artifact_missing`); Bình als 3 + content 7. Nhãn nguồn có thể ghép bằng `+` (`service._origin_label`).
- Router: tier `0_history` / `few_history` / `enough_history`, ngưỡng `routing.T_few_enough` = 10; strategy `POPULARITY`, `CONTENT+POPULARITY`, `ALS+CONTENT`; `fallbackReason` thuộc {`als_artifact_missing`, `no_content_candidates`, `filled_from_popularity`} hoặc null. API chưa trả ngưỡng T.
- Container `api`: `python:3.12-slim`, build context là gốc repo, mount đè `src/`, `configs/`. Repo **chưa có `.dockerignore`**; gốc repo có `movielens32m/` (1.7 GB) và một file zip 1.3 GB.
- Máy dev có Node 22.17 / npm 11.17.
- Ràng buộc từ các change trước, vẫn giữ: chạy offline (không CDN, không Google Fonts; test hiện có kiểm `/app` không chứa URL `http(s)://`); tương phản ≥ 4.5:1; vùng bấm ≥ 40 px (44 px trên màn hẹp); trang user không có thuật ngữ kỹ thuật; persona không phải xác thực (PRD §3.2 cấm suy diễn nhân khẩu học).
- Design system đã lọc qua `ui-ux-pro-max` (màu, font, quy tắc UX), có số đo tương phản ở mục D-8.

## Goals / Non-Goals

**Goals:**
- Hai trang React tách biệt, đủ chức năng như hai trang cũ (danh sách đối chiếu ở tasks), đẹp và nhất quán theo một design system.
- Trang user kể được câu chuyện "hệ thống lai" cho mọi loại user, kể cả khi chỉ có một nguồn.
- Admin có khung sidebar sẵn chỗ cho các mục của change explainer.
- Ai chạy `docker compose up --build` cũng có giao diện mới, không cần cài Node.
- Chuyển từ trang cũ sang trang mới an toàn: chạy song song, đổi bằng cờ cấu hình, trang cũ luôn còn ở `/legacy`.

**Non-Goals:**
- Khung giải thích gợi ý, tìm/lọc danh mục phim, thống kê thể loại, điểm trung bình/WR từng phim, sửa tie-break, cách chọn phim mới theo thể loại. Các việc này thuộc change `admin-recommendation-explainer`.
- Endpoint mới (ngoài một trường `tierThreshold`), đổi logic gợi ý, xác thực, poster, chế độ tối, SSR, đa ngôn ngữ.
- Xoá trang cũ. Việc đó để một change sau khi bản mới đã chạy ổn.

## Decisions

### D-1. Một project Vite, hai trang (multi-page)

```
web/
├── app.html, admin.html          ← hai entry; build ra 2 bundle riêng
├── vite.config.ts                ← base "/ui/", rollup input {app, admin}, dev proxy
├── src/
│   ├── shared/
│   │   ├── api/                  client fetch, schema.d.ts (sinh từ OpenAPI), query keys
│   │   ├── hooks/                useRecommendations, useRateMovie, useRatingStatus,
│   │   │                         useRatingHistory, useSystemStatus, useRetryEventId
│   │   ├── lib/                  genre.ts (màu/icon), movie.ts (tách năm), sources.ts
│   │   └── ui/                   component shadcn + MovieCard, GenreTile, StarRating
│   ├── user/                     App, AccountChooser, CreateAccount, TierBanner, Feed,
│   │                             RatingHistory, account store
│   └── admin/                    App (shell + sidebar), sections/*, cases.ts, eventLog
```

**Vì sao:** người dùng tách hai vai, user không phải tải code admin, nhưng hai trang dùng chung client, kiểu dữ liệu và component.

**Phương án đã cân nhắc:**
- *Một SPA có router (`/app/*`, `/admin/*`):* một bundle, admin lộ ra cho user, khó gắn cờ chặn theo trang.
- *Hai project riêng:* trùng code client, hook và component.
- *Next.js:* có SSR mà không cần, thêm một tiến trình Node lúc chạy.

### D-2. Thư viện

| Việc | Chọn | Ghi chú |
|---|---|---|
| UI | React 19 + TypeScript strict | |
| Build | Vite | `base: "/ui/"` để mọi asset nằm dưới `/ui/assets/` |
| Style | Tailwind CSS v4 (`@tailwindcss/vite`) + shadcn/ui | Component shadcn được chép vào `src/shared/ui`; mạng chỉ cần lúc chép, không cần lúc chạy |
| Dữ liệu | TanStack Query v5 | Cache, polling, tải lại khi focus |
| Icon | lucide-react | Đóng gói trong bundle |
| Toast | sonner (qua shadcn) | `toast.success` / `toast.error` |
| Font | `@fontsource/fira-sans` (400/500/600), `@fontsource/fira-code` (400/500) | Tự đóng gói. `fonts.css` được sinh từ CSS đầy đủ của Fontsource (có `unicode-range`; các file CSS theo từng subset thì không có) và chỉ giữ latin, latin-ext, vietnamese cho Fira Sans, latin cho Fira Code, chỉ woff2. Đã kiểm dấu tiếng Việt: đạt |
| Kiểu API | `openapi-typescript` | Sinh `schema.d.ts` từ `/openapi.json` và **commit** file sinh ra, để build trong Docker không cần API chạy |
| Điều hướng admin | Hook nhỏ đọc `location.hash` | Sáu mục, không cần thư viện router |
| Test | Vitest + Testing Library | |

### D-3. Lớp dữ liệu thay cho JS tự viết

| Trang cũ | Trang mới |
|---|---|
| `poll()` gọi `/ratings/{id}` mỗi giây tới khi hết hạn | lớp `RatingFlow` (TypeScript thuần, `lib/ratingFlow.ts`) cùng hook `useRatingFlow`: POST rồi poll 1 s, dừng khi `applied` hoặc quá `demo.ratingPollTimeoutSeconds`. Không dùng `refetchInterval` vì trạng thái chờ phải sống ngoài từng thẻ: khi feed tải lại, thẻ có thể chuyển sang hàng khác và bị mount lại, nhưng sao vẫn phải khoá |
| Bắt `visibilitychange` để tải lại feed | `refetchOnWindowFocus` của TanStack Query |
| Chặn tải lại khi đang có rating chờ (tránh vẽ lại DOM mở khoá sao) | Không cần chặn nữa. Trạng thái "đang chờ" giữ trong `RatingFlow` theo `movieId` (snapshot bất biến, đọc bằng `useSyncExternalStore`), nên vẽ lại hay chuyển hàng không làm mất khoá. Có test cho việc này |
| `rateMovie`, `addMovie`, `deleteMovie` rồi tải lại tay | `useMutation` + `invalidateQueries` cho feed, lịch sử, trạng thái hệ thống |
| `retryIds` / `eventIdFor` / `forgetRetryIds` | `useRetryEventId`: cùng quy tắc của change review. Dùng lại `eventId` cho cùng (user, phim, số sao) sau kết quả khác 202/422; xoá **mọi** id của (user, phim) khi nhận 202 hoặc 422; xoá hết khi đăng nhập hoặc đăng xuất |
| `refreshSystem()` | `useSystemStatus`: poll 10 s, chỉ khi đang mở mục Tổng quan hoặc Model |

Client fetch trả về `{ ok, status, body }` như trang cũ; lỗi mạng thành `status: 0`. Không dùng `useEffect` để tính state suy ra (quy tắc React của skill).

### D-4. Tài khoản trên trang user (giữ đúng hành vi cũ)

- Persona An (700008), Bình (1), Chi (127249) mô tả theo gu xem phim, không bịa nhân khẩu học. Có dòng ghi rõ "tài khoản demo, không mật khẩu".
- Tạo tài khoản: tên 1–40 ký tự; chọn `userId` ngẫu nhiên trong 500000–599998 mà `GET /users/{id}/ratings` có `total = 0` (tối đa 5 lần thử).
- Phiên theo tab bằng `sessionStorage`; danh sách tài khoản đã tạo bằng `localStorage`. Mọi lần đọc ghi bọc try/catch, lỗi lưu trữ không làm hỏng trang.
- Context React chỉ giữ tài khoản (dữ liệu toàn cục, ít đổi). Dữ liệu API không đưa vào Context.

### D-5. Feed của trang user

**Banner theo tier** (vùng `aria-live="polite"`). Số phim đã chấm lấy từ `GET /users/{id}/ratings`; ngưỡng T từ `/debug/system`:

| Điều kiện | Nội dung (không thuật ngữ kỹ thuật) | Thanh tiến độ |
|---|---|---|
| `0_history` | "Bạn chưa chấm phim nào. Đây là những phim được nhiều người đánh giá cao. Chấm một phim bạn đã xem để nhận gợi ý theo gu của bạn." | 0/T |
| `few_history` | "Bạn đã chấm N phim. Gợi ý đang dựa trên những phim giống phim bạn thích. Chấm thêm T−N phim để nhận gợi ý dành riêng cho bạn." | N/T |
| `enough_history`, không fallback | "Gợi ý được học từ N phim bạn đã chấm và từ những người có gu giống bạn." | ẩn |
| `fallbackReason = als_artifact_missing` | "Bạn đã chấm N phim. Hệ thống chưa có hồ sơ riêng cho bạn, nên tạm gợi ý theo phim giống phim bạn thích." | ẩn |
| `no_content_candidates` | "Chưa tìm được phim giống phim bạn thích, nên đây là những phim được nhiều người đánh giá cao." | theo tier |
| `filled_from_popularity` | Thêm một dòng: "Một vài phim phổ biến được thêm vào cho đủ danh sách." | — |

**Chia hàng.** Nguồn chính của mỗi gợi ý = nguồn đứng đầu trong thứ tự `new > als > content > popularity` có mặt trong nhãn (nhãn ghép như `als+content` thành `als`). Có ít nhất hai nguồn chính thì mỗi nguồn một hàng, đặt tên theo nhãn lý do đã dùng ở trang cũ: "Dành riêng cho bạn", "Giống phim bạn đã thích", "Đang được yêu thích", "Mới thêm". Hàng xếp theo hạng tốt nhất trong hàng. Chỉ một nguồn thì hiện một lưới dưới đúng tiêu đề đó. Mọi thẻ giữ số hạng gốc `#n`, nên thứ tự của hệ thống không bị che đi.

**Thẻ phim:** ô thể loại (D-6), tên (tối đa 2 dòng), năm, chip thể loại, nhãn lý do, huy hiệu "Mới" (nền `#FBBF24`, chữ tối), nhóm sao `role="radiogroup"` đi bằng phím mũi tên; mỗi sao là vùng bấm 40 px (44 px dưới 640 px) có `aria-label`. Khi gửi: khoá sao của thẻ, hiện "Đang cập nhật gợi ý…"; 202 → toast success tự tắt sau 4 s; lỗi → toast error kèm nút thử lại (dùng lại `eventId`); hết hạn chờ → "Đánh giá đã lưu, gợi ý sẽ cập nhật sau."

**Còn lại:** skeleton giữ đúng kích thước thẻ khi tải; mục "Phim bạn đã đánh giá" (50 phim gần nhất, kèm tổng số) và trạng thái rỗng cho tài khoản mới; link "bỏ qua tới nội dung chính".

### D-6. Ô màu theo thể loại

Thể loại chính = thể loại đầu tiên trong chuỗi `genres`. 19 thể loại của MovieLens gom thành 8 họ màu: nền ô dùng tông 100, icon tông 700 (đồ hoạ cần ≥ 3:1 trên nền ô, kiểm bằng script lúc làm). Mỗi thể loại một icon lucide; tên icon kiểm lại khi cài.

| Họ màu | Thể loại |
|---|---|
| blue | Drama, Film-Noir |
| amber | Comedy, Children, Animation |
| red | Action, War, Western |
| violet | Sci-Fi, Fantasy, IMAX |
| slate | Crime, Mystery, Thriller |
| rose | Romance, Musical |
| emerald | Adventure, Documentary |
| stone | Horror, `(no genres listed)` |

Màu không phải tín hiệu duy nhất: ô luôn có icon và tên thể loại. Năm tách bằng `\((\d{4})\)\s*$` ở cuối tên; không có thì bỏ trống.

### D-7. Khung admin

```
┌──────────────┬──────────────────────────────────────────────┐
│ MovieLens    │ <tiêu đề mục>      model v1.0.0 · [Trang user]│
│ Quản trị     ├──────────────────────────────────────────────┤
│ ▸ Tổng quan  │                                              │
│ ▸ Case test  │            nội dung của mục                  │
│ ▸ Người dùng │                                              │
│ ▸ Phim       │                                              │
│ ▸ Model      │                                              │
│ ▸ Nhật ký    │                                              │
│ (chỗ trống   │                                              │
│  cho change  │                                              │
│  explainer)  │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

| Mục (hash) | Nội dung | Nguồn dữ liệu |
|---|---|---|
| Tổng quan `#/overview` | Thẻ KPI: model đang chạy, số version, tiến độ retrain (pending/nMin, watermark), số phim demo, trạng thái API | `/debug/system`, `/health` |
| Case test `#/cases` | Chọn 1 trong 12 case (`free`, `c1`–`c9`, `als`, `noals`), thẻ kỳ vọng/quan sát, lưới gợi ý có chấm sao | Nội dung 12 case chép nguyên văn từ `demo.html` sang `admin/cases.ts`; dữ liệu từ `/recommendations`, `/debug/users` |
| Người dùng `#/users/<id>` | Ô nhập userId + lối tắt persona; gợi ý hiện tại; "bên trong hệ thống" (tier, interaction_count, recent/positive, pipeline `lastBatchId`/`lastRunAt`) | `/recommendations`, `/debug/users` |
| Phim `#/movies` | Danh sách phim demo; thêm phim bằng dialog (tên, chọn thể loại, kiểm tra khi rời ô, lỗi `role=alert`); xoá phải xác nhận vì không hoàn tác được | `/debug/system`, `POST/DELETE /movies` |
| Model `#/models` | Bảng version, gate checks hiển thị icon + chữ PASS/FAIL, tiến độ retrain | `/debug/system` |
| Nhật ký `#/log` | Thao tác trong phiên (gửi rating, applied, thêm/xoá phim) có giờ | Chỉ phía trình duyệt, lưu `sessionStorage` |

Bảng có thanh cuộn ngang trên màn hẹp; sidebar thu thành ngăn kéo dưới 1024 px. Danh sách thể loại cho dialog thêm phim là hằng số giống `MOVIELENS_GENRES` của API; API vẫn là nơi kiểm tra cuối (422).

### D-8. Design system (đã lọc từ `ui-ux-pro-max`)

| Token | Giá trị | Đo |
|---|---|---|
| background / surface / border | `#F8FAFC` / `#FFFFFF` / `#E2E8F0` | — |
| foreground | `#0F172A` | 17.06:1 trên background |
| muted-foreground | `#475569` (không dùng màu nhạt hơn `#64748B`) | 7.58:1 trên trắng |
| primary / primary-hover | `#2563EB` / `#1E40AF`, chữ trắng | 5.17:1 / 8.72:1 |
| highlight ("Mới", cảnh báo nhẹ) | nền `#FBBF24` chữ `#0F172A` | 10.69:1 |
| accent (shadcn: nền khi hover menu/chọn) | nền `#EFF6FF` chữ `#1E40AF` | đo bằng `npm run check` |
| warning text | `#B45309` | 5.02:1 |
| success / destructive | tông 700 của green / red, kiểm ≥ 4.5:1 khi làm | — |

- Token đặt ở biến CSS theme của shadcn (Tailwind v4 `@theme`); component chỉ dùng tên token (`bg-primary`), không mã màu rời rạc.
- Chữ: Fira Sans cho giao diện; Fira Code cho số, ID, điểm, `eventId`. Thân chữ trang user 16 px; bảng admin 14 px (màn desktop); line-height 1.5.
- Chuyển động 150–300 ms, chỉ `transform`/`opacity`; tắt khi `prefers-reduced-motion`. Hover đổi màu hoặc bóng, không phóng to làm xê dịch bố cục.
- Lớp xếp chồng: 10 nội dung nổi · 20 sidebar/header · 40 dialog · 50 toast.
- Focus: vòng `ring-2` màu primary và lệch 2 px, luôn thấy khi điều hướng bằng phím. Mọi thứ bấm được có `cursor-pointer`.
- Không dùng emoji làm icon.

Đã loại khỏi gợi ý tự động của skill: pattern "App Store Style Landing" và "AI Personalization Landing" (là trang quảng bá); style "Vibrant & Block-based" và bảng màu cyan/xanh lá (chữ trắng 3.68:1 và 2.28:1, trượt AA); Righteous/Poppins (Google Fonts, chưa chắc có dấu tiếng Việt); nút cam chữ trắng (2.15:1).

### D-9. FastAPI phục vụ bản build, đổi bằng cờ

```
 WEB_DIST_DIR (env, mặc định /app/web-dist; dev: web/dist)
   ├── app.html, admin.html
   └── assets/*.js|css|woff2          (Vite output; its HTML refers to them as /ui/assets/...)
 configs/serving.yaml  api.ui: "legacy" | "react"   (mặc định "legacy")

 GET /ui/assets/*    → StaticFiles của bản build
 GET /app-next       → bản build app.html     (404: demo tắt hoặc chưa build)
 GET /admin-next     → bản build admin.html   (404: demo tắt hoặc chưa build)
 GET /app            → api.ui=react và đã build ? bản mới : static/app.html
 GET /admin, /demo   → api.ui=react và đã build ? bản mới : static/demo.html
 GET /legacy/app     → static/app.html  luôn    (404 khi demo tắt)
 GET /legacy/admin   → static/demo.html luôn    (404 khi demo tắt)
```

- Route `GET /ui/{path}` chỉ phục vụ file trong `dist/assets/` (từ chối đường dẫn thoát ra ngoài) và trả 404 cho mọi `/ui/*` khi `api.demo_enabled` tắt, để trang tắt demo không lộ mã giao diện. Dùng route thay cho `StaticFiles` vì thư mục build có thể chưa tồn tại lúc khởi động.
- `api.ui = "react"` mà thiếu bản build thì quay về trang cũ và ghi một dòng cảnh báo vào log. Đổi qua lại chỉ cần sửa cờ và restart `api`.
- Unit test chạy được khi chưa build: mặc định là `legacy`; test cho bản mới dùng một thư mục build giả tạm thời.

**Phương án đã cân nhắc:** container nginx riêng (thêm hạ tầng, phải đồng bộ cờ chặn); chạy `vite preview` khi demo (cần Node lúc chạy); thay luôn `/app` mà không có cờ (không có đường lùi nhanh khi demo).

### D-10. Build

- **Docker:** `docker/api.Dockerfile` thêm stage `FROM node:22-alpine AS web`: `npm ci` (theo lockfile), rồi `npm run build`. Stage cuối `COPY --from=web` bản build vào `/app/web-dist`, nằm ngoài các thư mục bị mount đè. Stage node không vào image cuối.
- **`.dockerignore` mới:** chặn `movielens32m/`, `*.zip`, `.venv*`, `web/node_modules`, `web/dist`, `.omc/`, `.claude/`, `logs/`, `.git/`. Repo hiện chưa có file này, trong khi build context là cả repo.
- **Dev:** `npm run dev` (cổng 5173) proxy các đường dẫn API (`/recommendations`, `/ratings`, `/users`, `/debug`, `/movies`, `/health`, `/openapi.json`) sang `http://127.0.0.1:8088`, nên không cần bật CORS. `npm run gen:api` sinh lại kiểu từ API đang chạy.
- **Lockfile** được commit; phiên bản thư viện cố định.

### D-11. Trường `tierThreshold`

`DemoSettingsOut` thêm `tierThreshold: int` lấy từ `routing.T_few_enough`. Đây là route demo-only và chỉ thêm trường, nên không client cũ nào hỏng. Trang user dùng nó cho banner, không còn số 10 cố định trong code giao diện.

### D-12. Kiểm thử và tiêu chí chuyển `api.ui` sang `react`

- **Vitest** cho phần thuần: gom nguồn chính và chia hàng (gồm nhãn ghép), nội dung banner cho mọi dòng của bảng D-5, tách năm, ánh xạ thể loại ra màu/icon (đủ 19 + `(no genres listed)`), `useRetryEventId`, kho tài khoản khi `localStorage` ném lỗi, khoá sao còn nguyên sau khi feed vẽ lại.
- **pytest** cho route: `-next` khi có/không bản build; `/app` theo cờ và tự quay về; `/legacy/*`; `/ui/assets` bị chặn khi demo tắt; `tierThreshold` có trong `/debug/system`.
- **Trên trình duyệt** (bản build trong Docker): đủ danh sách chức năng cũ (tasks 7.x); bàn phím đi hết trang; 375 / 768 / 1024 / 1440 px không tràn ngang; script tương phản cho mọi token và ô thể loại; `grep` bản build không có `http(s)://` trỏ ra ngoài; `prefers-reduced-motion`.
- **Ngân sách kích thước:** JS của trang user ≤ 250 KB sau gzip, admin ≤ 350 KB. Đo thật và ghi vào evidence.
- Chỉ khi tất cả đạt mới đổi `api.ui` sang `react`.

## Risks / Trade-offs

- **[Thêm toolchain Node vào dự án Python]** → Build nằm trong Docker; chỉ ai sửa giao diện mới cần Node ở máy. README ghi rõ.
- **[Image `api` build lâu hơn]** → Stage node có cache theo lockfile; image cuối không chứa Node. `.dockerignore` giảm build context.
- **[Hai bộ giao diện cùng tồn tại một thời gian]** → Trang cũ đóng băng, chỉ sửa lỗi; xoá ở change sau.
- **[Fira Sans thiếu dấu tiếng Việt]** → Kiểm ngay ở bước cài font; thiếu thì dùng font hệ thống như trang cũ.
- **[Kiểu sinh từ OpenAPI lệch với API]** → File sinh được commit; thêm script so sánh lại khi API đổi (chạy tay trong task).
- **[shadcn/ui CLI cần mạng lúc chép component]** → Chỉ lúc phát triển; code đã chép nằm trong repo, build và chạy không cần mạng.
- **[Bản mới có lỗi lúc demo]** → Đổi `api.ui` về `legacy` và restart `api`; `/legacy/*` luôn có sẵn.

## Migration Plan

1. Thêm `web/`, route `-next`, `/legacy/*`, `/ui/assets`, cờ `api.ui` (mặc định `legacy`), `.dockerignore`, stage node. Lúc này không đường dẫn cũ nào đổi hành vi.
2. Làm trang user, rồi trang admin, kiểm trên `/app-next` và `/admin-next`.
3. Chạy hết checklist D-12, ghi evidence.
4. Đổi `api.ui` sang `react` trong `configs/serving.yaml` (đây là cấu hình được commit, khác cờ `demo_enabled`). `/app` và `/admin` trả bản mới, trang cũ ở `/legacy/*`.
5. Rollback: đặt `api.ui: legacy` và restart `api`.

## Open Questions

- Khi nào xoá hẳn trang cũ và các route `/legacy/*`? Đề xuất: một change riêng sau khi giao diện mới qua ít nhất một buổi demo.
- Có cần chế độ tối? Hiện là non-goal; token đã tách nên thêm sau không phải viết lại.
- Change explainer sẽ thêm mục Thể loại và biểu đồ (Recharts); quy tắc biểu đồ đã ghi ở design system của skill (cột ngang sắp giảm dần có nhãn số, cột chồng thay pie, luôn kèm bảng). Phần cài Recharts để cho change đó.
