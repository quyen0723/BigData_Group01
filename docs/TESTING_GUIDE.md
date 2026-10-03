# TESTING_GUIDE.md — Tự test phần Person 2 (không cần Claude)

> Mọi lệnh dưới đây đã **chạy thật và verify PASS** trong phiên làm việc trước
> (xem `evidence/p2_*`, `CHECKLIST_Person2.md`). Đây là bản sao lại để bạn tự
> chạy, không cần chờ Claude. Chạy trên **PowerShell**, đứng ở gốc repo
> (`E:\Master\big-data\final\BigData_Group01`).

## 0. Điều kiện trước khi test

1. Docker Desktop đang mở, báo "Engine running".
2. Bundle `movielens32m\` đã có ở gốc repo (đã tải từ Drive).
3. Bật stack:
   ```powershell
   docker compose -f docker/docker-compose.yml up -d
   docker compose -f docker/docker-compose.yml ps
   ```
   Cả 6 dòng (`mongo`, `kafka`, `spark`, `streaming`, `api`, `mongo-express`) phải
   `Up`; `mongo`, `kafka`, `api`, `streaming` phải `healthy`. `streaming` là
   pipeline Structured Streaming, tự chạy cùng stack (xem mục 2b).

Nếu đây là **lần đầu tiên** sau khi tạo volume mới (Mongo rỗng), cần nạp dữ liệu
trước — xem README.md mục "Getting started — Person 2" bước 2. Nếu Mongo đã có
dữ liệu từ trước (volume cũ còn giữ), bỏ qua, sang mục 1 luôn.

---

## 1. Giao diện xem trực quan

| Cái gì | Ở đâu | Ghi chú |
|---|---|---|
| **Swagger UI** (test API bằng giao diện, không cần gõ lệnh) | http://127.0.0.1:8088/docs | Tự có sẵn từ FastAPI, bấm "Try it out" ngay trên trình duyệt |
| ReDoc (tài liệu API dạng đọc) | http://127.0.0.1:8088/redoc | Chỉ để đọc, không test được |
| **MongoDB — mongo-express** (xem + CRUD trên trình duyệt, không cần cài app) | http://127.0.0.1:8081 | Đăng nhập bằng `ME_CONFIG_BASICAUTH_USERNAME` / `_PASSWORD` trong file `.env` ở gốc repo. Chỉ mở trên máy mình (127.0.0.1), không truy cập được từ máy khác |
| MongoDB — Compass (app desktop, tuỳ chọn) | Cài [MongoDB Compass](https://www.mongodb.com/try/download/compass), kết nối `mongodb://127.0.0.1:27017` | Không cần mật khẩu |
| MongoDB — terminal | `docker exec -it movielens-mongo mongosh movielens` | Có sẵn, không cần cài gì |
| Kafka | Không có UI, chỉ có CLI (`docker compose exec kafka /opt/kafka/bin/kafka-topics.sh ...`) | Nếu cần xem trực quan, có thể thêm `kafka-ui` sau |

**Cách nhanh nhất để tự test mà không cần thuộc lệnh gì**: mở
http://127.0.0.1:8088/docs, bấm vào `GET /recommendations/{userId}`, bấm "Try
it out", gõ `userId` bất kỳ, bấm "Execute" — xem kết quả ngay trên trình duyệt.

### Sửa dữ liệu Mongo bằng tay (mongo-express / Compass) — đọc trước khi CRUD

mongo-express bật CRUD đầy đủ. Công cụ không nguy hiểm, nhưng **API đọc thẳng
từ các collection này**, nên sửa tay tức là đi vòng qua thành phần vốn chịu
trách nhiệm ghi vào đó:

| Sửa tay collection | Chuyện gì xảy ra | Cách ghi đúng / cách khôi phục |
|---|---|---|
| `serving_meta` | API đổi version ngay, hoặc trả `503` nếu doc sai | `python -m loaders.bootstrap_registry --version v1.0.0` |
| `user_history` | Bị **ghi đè** ở lần user đó rate tiếp theo (streaming tính lại từ `user_rated`) | Để streaming tự cập nhật |
| `user_rated` | Có tác dụng loại phim ngay, nhưng **không** vào Curated Parquet → lần retrain sau model không học được | Rate qua `POST /ratings` (bấm ⭐ trên `/demo`) |
| `popular_movies`, `similar_movies`, `user_recommendations` | API trả kết quả đã sửa, lệch với model thật | `python -m loaders.load_artifacts --artifact <popular\|similar\|als_topn> --version v1.0.0` |

- **Không bấm Reindex / Compact trên `user_rated`** (32 triệu doc): khoá Mongo
  một lúc lâu, API đứng theo — đặc biệt nguy hiểm khi đang demo.
- Muốn tập CRUD thoải mái: tạo database riêng (ví dụ `sandbox`) ngay trong
  mongo-express, đừng tập trên `movielens`.
- Demo "dữ liệu thay đổi sau khi rate": mở collection `rating_events`, bấm ⭐
  trên `/demo`, rồi refresh — doc mới xuất hiện kèm `batchId` và `ingestedAt`.

---

## 2. Toàn bộ route hiện có

| Method | Route | Tham số | Trả về |
|---|---|---|---|
| GET | `/health` | — | `{"status": "ok"}` |
| GET | `/recommendations/{userId}` | `userId` (path, bắt buộc, > 0) · `k` (query, tuỳ chọn, mặc định 10, 1–50) | JSON: `userId, tier, strategy, modelVersion, generatedAt, fallbackReason, recommendations[]` |

Từ change `add-demo-web-client`, có thêm 4 route: `POST /ratings`,
`GET /ratings/{eventId}` (luôn bật), và các route demo-only (404 khi
`api.demo_enabled` tắt, xem mục 2b): `GET /demo`, `GET /debug/users/{userId}`,
`GET /debug/system`, `POST /movies`, `DELETE /movies/{movieId}`, `GET /app`,
`GET /admin`, `GET /users/{userId}/ratings`. Từ change `rebuild-ui-react` có thêm
`GET /app-next`, `GET /admin-next` (luôn là bản React), `GET /legacy/app`,
`GET /legacy/admin` (luôn là trang cũ) và `GET /ui/assets/*` (file build), cũng 404 khi demo tắt.

**Hợp đồng của `POST /ratings`.** `202` nghĩa là Kafka đã nhận, chưa phải đã áp dụng
(hỏi `GET /ratings/{eventId}`). `503` kèm `kafka delivery timed out` nghĩa là
**kết quả chưa biết**: tin nhắn đã nằm trong hàng đợi của producer và vẫn có thể tới
Kafka sau phản hồi. Muốn thử lại an toàn, gửi lại **cùng `eventId`**; ledger gộp các bản
gửi thành một. `eventId` là tuỳ chọn, nhưng khi bỏ trống server sinh UUID mới cho
mỗi request, nên thử lại sẽ thành một đánh giá khác. Trang `/app` giữ `eventId` cho lần
thử lại cùng một đánh giá (cùng user, phim và số sao) và đổi id sau khi nhận `202`.

---

## 2b. Demo bằng giao diện (khuyên dùng cho buổi thuyết trình)

Đây là cách nhanh nhất để giám khảo **thấy** hệ thống hoạt động mà không cần
nhìn lệnh terminal: hai trang web (React, đã build sẵn trong image `api`), tự
phục vụ bởi chính API, không cần cài gì thêm, không cần internet (font cũng đóng
gói sẵn). Xem "Giao diện React" ngay dưới phần này để biết đường dẫn, cờ `api.ui`
và cách quay về trang cũ.

**Bước 0 — bật cờ demo (mặc định tắt vì lý do bảo mật, xem
`docs/DEPLOYMENT_DESIGN.md` §Security):**
```powershell
# Sửa configs/serving.yaml: api.demo_enabled: false -> true
docker compose -f docker/docker-compose.yml restart api
```
Mở trình duyệt tới **http://127.0.0.1:8088/demo**.

**5 bước kịch bản demo:**
1. Ở ô **Case test**, chọn lần lượt *1. User có tài khoản, chưa rating*, *Đã có
   rating và có ALS (user 1)* và *Đủ lịch sử nhưng thiếu ALS (user 127249)* để
   cho thấy 3 tier khác nhau ở panel "Bên trong hệ thống": `0_history/POPULARITY`,
   `enough_history/ALS+CONTENT`, và `enough_history/CONTENT+POPULARITY` với
   `fallbackReason: als_artifact_missing` tô màu cam (chuỗi hạ cấp khi thiếu
   ALS document). Mỗi case có thẻ giải thích theo bảng 9 use case của nhóm.
2. Chọn lại 1 user (ví dụ *user 1*), đọc bảng gợi ý bên trái — mỗi thẻ có
   title/genres/rank/source, viền màu theo thể loại chính. (Danh sách đầy đủ
   các case và cách demo từng case: xem mục "Demo theo case test" bên dưới.)
3. Bấm ⭐ trên 1 thẻ bất kỳ. Nhật ký bên phải ghi ngay
   `→ Kafka ✓ (202, eventId=...)` — đây là bằng chứng trực quan cho tính bất
   đồng bộ (202 = đã vào hàng đợi, chưa áp dụng).
4. Đợi (trang tự poll mỗi giây, tối đa `api.rating_poll_timeout_seconds` = 60
   giây). Khi áp dụng xong, trang **tự
   tải lại**: phim vừa rate biến mất khỏi danh sách, `interaction_count` tăng,
   nếu đủ để đổi tier thì dòng `tier` sẽ nhấp nháy giá trị mới.
5. **(Tuỳ chọn) minh hoạ fault-tolerance** — mở 1 cửa sổ terminal khác và dừng
   service streaming:
   ```powershell
   docker compose -f docker/docker-compose.yml stop streaming
   ```
   Quay lại trình duyệt, bấm ⭐ 1 lần nữa. Sau 60 giây, nhật ký hiện gợi ý
   *"Streaming pipeline có đang chạy không?"* — đây là hành vi **đúng thiết
   kế**, không phải lỗi. `stop` là dừng thủ công nên Docker **không** tự bật lại
   (đúng ý khi demo). Bật lại:
   ```powershell
   docker compose -f docker/docker-compose.yml start streaming
   ```
   Sau khoảng 1–2 phút pipeline khởi động và bắt kịp. Bấm "Tải gợi ý" lại — rating
   vẫn được áp dụng (event nằm an toàn trong Kafka, pipeline đọc tiếp từ
   checkpoint), đúng tinh thần eventual consistency.

**Streaming là một service tự chạy** (`streaming` trong docker-compose): nó khởi
động cùng `docker compose up -d`, và **tự chạy lại** sau khi Docker Desktop khởi
động lại hoặc khi tiến trình Spark sập — không còn phải mở terminal riêng. Xem
trạng thái và log:
```powershell
docker compose -f docker/docker-compose.yml ps streaming
docker compose -f docker/docker-compose.yml logs -f streaming
```
`ps` phải báo `healthy`; log có các dòng `serve_batch[N]: committed`.
**Không** chạy `python -m streaming.pipeline` bằng tay nữa: pipeline là singleton
(một checkpoint), hai bản chạy cùng lúc sẽ làm hỏng checkpoint.

**Độ trễ áp dụng rating (đã đo, xem `evidence/p2_streaming_latency.txt`):** 12–44
giây, trung vị khoảng 20 giây, không phải 5–10 giây. Event đi qua hai stream query
nối tiếp (Kafka → `raw_events/` → `serve_batch`), mỗi query chạy một batch khoảng
10 giây trên Docker Desktop/WSL2; vì batch dài hơn trigger 5 giây nên giảm trigger
không giúp gì. Khung chờ của trang demo là 60 giây. Hai điều làm độ trễ tệ hơn rõ
rệt (1–4 phút) và cần tránh:
- **Không** chạy thêm lệnh `docker compose exec spark python -c "..."` nào khác
  song song lúc đang demo — mỗi lệnh mở 1 Spark session mới, tranh CPU với
  pipeline.
- Không để vòng lặp nền nào tự chạy lại job Spark (đã từng tạo 328 process zombie).

**Ngay trước giờ thuyết trình:** `docker compose ps` thấy `streaming` là `healthy`;
nếu vừa bật lại Docker Desktop, đợi khoảng 1–2 phút cho pipeline bắt kịp rồi mới
bấm ⭐ lần đầu (lần xử lý đầu tiên sau khi khởi động chậm nhất).

Nếu quá giờ demo mà stack không lên kịp: dùng video quay sẵn (mục 3.4 trong
`openspec/changes/add-demo-web-client/tasks.md`) làm phương án dự phòng.

### Giao diện React (change `rebuild-ui-react`)

Hai trang `/app` (người dùng) và `/admin` (quản trị, cũng là `/demo`) là bản React xây từ thư mục `web/`.
Dữ liệu và API không đổi; chỉ giao diện đổi. Các bước 1–5 ở trên vẫn đúng với trang mới (ô **Case test**,
chấm sao, nhật ký, phim biến mất khỏi danh sách); khác biệt nhìn thấy: nhật ký ở mục **Nhật ký** của
thanh bên và dải "Nhật ký gần đây" dưới mỗi case; sau khi rating được áp dụng hoặc phim demo thay đổi, nhật ký
ghi cái gì đổi trong danh sách (ví dụ `tier đổi: 0_history → few_history`, `phim MỚI movieId=… xuất hiện ở hạng 3`);
thêm/xoá phim demo qua hộp thoại (xoá phải xác nhận).

| Địa chỉ | Trả về |
|---|---|
| `/app`, `/admin`, `/demo` | theo `api.ui` trong `configs/serving.yaml`: `"react"` (mặc định) hoặc `"legacy"` |
| `/app-next`, `/admin-next` | luôn bản React (để so sánh cạnh trang cũ) |
| `/legacy/app`, `/legacy/admin` | luôn trang cũ (tệp tĩnh) |

Tất cả đều 404 khi `api.demo_enabled: false`.

**Quay về trang cũ (rollback)** — chỉ cần đổi cờ rồi khởi động lại `api`, không cần build:
```powershell
# configs/serving.yaml: api.ui: "react" -> "legacy"
docker compose -f docker/docker-compose.yml restart api
```
**Sửa code giao diện rồi xem lại:** `docker compose -f docker/docker-compose.yml up -d --build api`
(lần build đầu cần mạng để `npm ci`; build tự chạy kiểm tra dung lượng, tương phản, không tải tài nguyên
ngoài, và sẽ báo lỗi nếu trang người dùng lẫn mã admin). Chạy dev và test: `web/README.md`.

**Checklist xem nhanh (khoảng 5 phút):**
- [ ] `/app` hiện ba persona An, Bình, Chi kèm số phim đã đánh giá; chọn **An** → lời chào, banner "Bạn đã chấm N phim" (N = số rating hiện có của An, seed ban đầu là 3), hàng "Giống phim bạn đã thích".
- [ ] Chấm sao một phim: ngay lập tức hết bấm được và có "Đang cập nhật gợi ý…", toast "Đã lưu đánh giá…", khoảng 10–45 giây sau toast "Gợi ý của bạn đã được cập nhật", phim rời danh sách.
- [ ] Bàn phím: Tab đầu tiên tới "Bỏ qua phần đầu trang"; mỗi nhóm sao là một điểm dừng Tab, phím mũi tên / Home / End di chuyển giữa các sao.
- [ ] Chọn **Bình** thấy hai hàng ("Dành riêng cho bạn" và "Giống phim bạn đã thích"); **Chi** thấy banner "Hệ thống chưa có hồ sơ riêng" và không có từ kỹ thuật nào trên trang.
- [ ] `/admin`: sáu mục ở thanh bên (Tổng quan, Case test, Người dùng, Phim, Model, Nhật ký); đủ 12 case; case 3/4/9 có bảng phim demo, case 5/6 có vòng đời model.
- [ ] Thêm một phim demo (Crime + Drama) rồi xoá: hộp thoại xác nhận hiện trước, chưa có `DELETE` nào gửi đi trước khi bấm "Xoá phim".
- [ ] Thu nhỏ cửa sổ về 375 px và 768 px: không có thanh cuộn ngang; ở dưới 1024 px thanh bên của `/admin` thành ngăn kéo.
- [ ] Rollback: đặt `ui: "legacy"`, restart `api`, `/app` ra trang cũ; đặt lại `"react"`.

### Demo WR sống (change `live-weighted-popularity`)

**WR phục vụ gì.** User mới chưa có dữ liệu (tầng `0_history`) nhận danh sách phim phổ biến xếp theo *weighted rating*
`WR = v/(v+m)·R + m/(v+m)·C` (`v` số rating của phim, `R` điểm trung bình, `C = 3.5287` điểm TB cả tập train, `m = 1000`).
Công thức kéo điểm của phim ít người chấm về mức trung bình chung, nên Planet Earth (4.468 sao, 173 người chấm) không đứng
trên Shawshank (4.428 sao, 73,945 người chấm). Trước đây danh sách này là một file tĩnh Quyên tính offline. Khi `popularity.live` bật,
API tính WR từ **số liệu tập train (collection `movie_stats`) cộng các rating streaming đã áp dụng (ledger `rating_events`)**,
nên chấm rating thì danh sách đổi theo. Streaming, Kafka và schema ledger không đổi.

Mục **Phổ biến** và endpoint `/debug/popularity` là route demo-only: cần `api.demo_enabled: true` (xem Bước 0 của mục 2b), nếu không trang hiện "Không tải được danh sách phổ biến" (404).

**Chuẩn bị một lần** (khoảng 2–3 phút, quét 32M rating; *đừng làm giữa buổi demo*, nó tranh CPU với `streaming`; trong lúc nó ghi lại `movie_stats`, API tạm dùng artifact):
```powershell
docker compose -f docker/docker-compose.yml exec spark python -m loaders.build_movie_stats
```
Kỳ vọng: `22,399,368 ratings on 36,526 movies`, `checks: ... -> PASS`, rồi `OK: movielens.movie_stats: 36,526 movies + _meta`.
Loader từ chối ghi nếu số rating khác `n_train` của Quyên hoặc điểm TB khác `C` đã ghi (có `--dry-run` để chỉ kiểm). Sau đó đặt
`popularity.live: true` trong `configs/serving.yaml` và `docker compose -f docker/docker-compose.yml restart api`. Kiểm:
```powershell
python scripts/wr_live_demo.py check
```
Kỳ vọng `PASS (same 10 movies in the same order, WR within 0.0005)`: khi chưa có rating mới, danh sách sống **trùng** danh sách của Quyên.
Kiểm phía Mongo thật (pipeline ledger và bộ đọc `movie_stats`, trên collection nháp, không chạm dữ liệu thật): `.venv-serving\Scripts\python scripts/check_live_popularity_store.py` → `RESULT: PASS`.

**Kịch bản (khoảng 6 phút):**
1. `python scripts/demo_wr_explain.py`: số liệu thật của 10 phim ở danh sách cũ (trước WR) và WR của chúng; đổi `--m 0` để thấy thứ tự quay về điểm TB thô.
2. Admin → mục **Phổ biến** (`/admin#/popularity`): bảng top 10 với điểm TB (R), số rating (v), WR và hạng so với danh sách gốc, tự làm mới mỗi 3 giây.
   Bấm tên một phim để xem công thức thay số từng bước. Gõ `0` vào ô "Xem trước với m khác": Planet Earth (khoảng 175 rating) lên hạng 1,
   Shawshank hạng 2 (chỉ là xem trước, người dùng vẫn nhận danh sách thật). Bấm "Đặt lại".
3. `python scripts/wr_live_demo.py plan`: với từng cặp phim liền kề, cần bao nhiêu rating 5 sao để phim dưới vượt phim trên. Cặp sát nhất là
   hạng 9 Seven Samurai trên hạng 8 One Flew Over the Cuckoo's Nest: **khoảng 17 rating**. Các cặp khác cần từ 62 đến hàng nghìn.
4. `python scripts/wr_live_demo.py inject --movie 2019 --n 19`: gửi 19 rating 5 sao từ 19 user giả qua `POST /ratings`, chờ streaming áp dụng
   (đã đo **12–51 giây**, không tức thời), rồi in bảng trước và sau. Kỳ vọng: Seven Samurai lên hạng 8 (WR 4.2054 → 4.2065, số rating `12,795 (+19)`),
   Cuckoo's Nest xuống hạng 9; bảng admin tự đổi; một tài khoản mới ở `/app` thấy Seven Samurai ở hạng 8.
5. `python scripts/wr_live_demo.py spam --n 10`: nhồi 5 sao cho phim ít người chấm nhất trong top 50 theo điểm TB thô (Planet Earth). In WR sau +10 và +100 rating
   (khoảng 3.68 và 3.77, vẫn xa ngưỡng top 10 là 4.199) và số rating cần để vượt ngưỡng (cỡ 780). `--n 0` chỉ in kế hoạch, `--dry-run` không gửi gì.

**Điều phải nói đúng khi trình bày:**
- Chỉ **một cặp** đổi hạng được bằng ít rating; phim càng nhiều rating càng "nặng", các cặp khác cần hàng trăm đến hàng nghìn.
- WR **chống chịu, không miễn nhiễm**: Planet Earth cần cỡ 780 rating 5 sao (4,5 lần số rating thật) mới vào top 10.
- Rating không có hiệu lực ngay: đi qua Kafka và streaming (12–51 giây), rồi API làm mới danh sách (bộ nhớ đệm 2 giây).
- WR sống chỉ đổi danh sách phổ biến. Tầng few/enough (content, ALS) và phim mới không đổi.
- Bảng chỉ là tính toán trên số liệu tập train của Quyên cộng rating mới. Việc huấn luyện lại model vẫn do Quyên làm.

**Dọn dữ liệu giả sau khi demo — bắt buộc trước khi bàn giao retrain** (gói bàn giao lấy event từ ledger):
```powershell
.venv-serving\Scripts\python scripts/purge_demo_ratings.py            # chỉ đếm (dry run)
.venv-serving\Scripts\python scripts/purge_demo_ratings.py --yes      # xoá user 999200000..999299999 khỏi ledger, user_rated, user_history
.venv-serving\Scripts\python scripts/purge_demo_ratings.py --all-synthetic --yes    # cả dải 999,000,000..999,999,999 (gồm 999100001..10)
```
Script từ chối mọi dải ngoài 999,000,000–999,999,999. Bảng admin bỏ các rating đó sau chừng 2 giây. Parquet `curated_ratings` (phân vùng `year=2026`)
vẫn còn các dòng đó; muốn dọn thì **dừng `streaming` trước** (nó đang ghi vào cùng phân vùng):
```powershell
docker compose -f docker/docker-compose.yml stop streaming
docker compose -f docker/docker-compose.yml exec spark python -m loaders.purge_curated_synthetic --all-synthetic            # chỉ đếm
docker compose -f docker/docker-compose.yml exec spark python -m loaders.purge_curated_synthetic --all-synthetic --apply --streaming-stopped
docker compose -f docker/docker-compose.yml start streaming
```
Job viết lại phân vùng, giữ bản cũ ở `curated_ratings/_purge_old_year=2026` cho tới khi bạn xoá tay. Đã diễn tập trên bản sao (55 → 47 rating).

**Quay lại như cũ:** đặt `popularity.live: false` và restart `api`: user mới nhận lại danh sách artifact. `movie_stats` có thể để nguyên.
Nếu `movie_stats` bị thiếu hoặc lỗi đọc ledger, API tự dùng artifact (một cảnh báo trong log) và `/recommendations` vẫn trả 200.
Nếu Quyên đổi `m`, `C`, `min_support` hay cutoff thì chạy lại `build_movie_stats` rồi `check`.

### Test case kiểm hành vi hệ thống qua giao diện (change `movie-catalog-search`)

Phần này không phải kịch bản trình diễn: mỗi dòng là một **hành vi của hệ thống** cần kiểm, làm trên giao diện, có kết quả mong đợi để đối chiếu đúng/sai.
Công cụ: trang `/app` (người dùng), `/admin#/cases` (case test, hiện tier/strategy/nguồn từng phim), `/admin#/users/<id>` (trạng thái bên trong của user),
`/admin#/movies` (danh mục phim có tìm kiếm), `/admin#/popularity` (danh sách phổ biến), `/admin#/log` (nhật ký).
Cột **Nguồn**: **đo** = đã chạy trên stack thật, số liệu là số đo; **code** = suy ra từ code và test tự động, chưa chạy thật trên stack (cần bạn xác nhận).
Mỗi rating bạn chấm là dữ liệu thật trong Mongo; tài khoản tạo trên trang nằm ngoài dải user giả nên script dọn không xoá được: dùng vài tài khoản thử.

**Cách tìm một phim để chấm hoặc kiểm:** trên `/app` dùng ô **Tìm phim để chấm** (từ 2 ký tự hoặc chọn thể loại); trên `/admin#/movies` dùng bảng **Danh mục phim**
(tìm tên, lọc thể loại, sắp theo số rating, điểm TB hoặc WR).

**1. Chọn tầng gợi ý** (`/admin#/cases`, ô userId)
| ID | Làm gì | Kết quả mong đợi | Nguồn |
|---|---|---|---|
| TC-01 | Case "1. User có tài khoản, chưa rating" | `tier=0_history · strategy=POPULARITY · interaction_count=0`; cả 10 phim nguồn `popularity`; không có `fallbackReason` | đo |
| TC-02 | Case tự do, nhập userId `99999999` (không tồn tại), bấm Tải gợi ý | Vẫn `0_history` với 10 phim phổ biến, không lỗi | đo |
| TC-03 | Case "2. User có rating mới" (An, 700008) | `few_history`, `CONTENT+POPULARITY`, `interaction_count` = số phim An đã chấm (hiện 6) | đo |
| TC-04 | Tạo tài khoản mới trên `/app`, chấm lần lượt phim (tìm bằng ô tìm), xem `#/users/<id>` sau mỗi lần áp dụng | Sau rating 1 đến 9: `few_history`. Sau rating thứ 10: `enough_history`, vẫn `CONTENT+POPULARITY` và `fallbackReason = als_artifact_missing` (user mới chưa có ALS) | code |
| TC-05 | Case "Đã có rating và có ALS (user 1)" | `enough_history`, `ALS+CONTENT`, 3 phim nguồn `als` + 7 nguồn `content`, không có `fallbackReason` | đo |
| TC-06 | Case "Đủ lịch sử nhưng thiếu ALS (user 127249)" | `enough_history`, `CONTENT+POPULARITY`, `fallbackReason = als_artifact_missing` (tô cam) | đo |
| TC-07 | Tải gợi ý hai lần liền cho cùng một user | Cùng danh sách, cùng thứ tự (kết quả ổn định) | code |

**2. Luồng rating** (`/app` hoặc `/admin#/cases`)
| ID | Làm gì | Kết quả mong đợi | Nguồn |
|---|---|---|---|
| TC-08 | Chấm sao một phim ở case 2 (An), mở `#/log` | Nhật ký: `★ rate …`, `→ Kafka ✓ (202, eventId=…)`, rồi `✓ applied (… batchId=…)` sau **12–51 giây** (không tức thời) | đo |
| TC-09 | Sau khi `applied`, nhìn danh sách của user đó | Phim vừa chấm **không còn** trong gợi ý; `interaction_count` tăng 1; "Phim bạn đã đánh giá" có phim đó | đo |
| TC-10 | Tìm phim đó bằng ô tìm trên `/app` | Thẻ phim hiện "Bạn đã chấm N sao" và vẫn chấm lại được | đo |
| TC-11 | Chấm lại một phim đã chấm (từ ô tìm) bằng số sao khác | Rating mới thay rating cũ, `interaction_count` **không** tăng (cùng một cặp user-phim) | code |
| TC-12 | Tài khoản mới chấm 5 sao một phim Crime/Thriller (ví dụ Pulp Fiction) | Sau `applied`: `few_history`, danh sách chuyển sang nguồn `content` gồm phim giống (hình sự, chính kịch) | code |
| TC-13 | Chấm sao một phim rồi tải lại trang ngay (khi chưa `applied`) | Sau khi tải lại, rating vẫn được áp dụng, không mất (event đã nằm trong Kafka) | code |

**3. Phim mới** (admin `#/cases` case 3, và tab `/app` của An)
| ID | Làm gì | Kết quả mong đợi | Nguồn |
|---|---|---|---|
| TC-14 | Thêm phim "Phim thử" (Crime + Drama), xem An | Phim ở **hạng 3** với nhãn **Mới**; nhật ký `phim MỚI … xuất hiện ở hạng 3` | đo |
| TC-15 | Thêm phim chỉ có thể loại Western, xem An | An **không** thấy (không trùng thể loại An thích) | đo |
| TC-16 | Thêm hai phim cùng khớp thể loại | An chỉ thấy **một** phim mới (chỉ có 1 chỗ), ở hạng 3 | code |
| TC-17 | Xem user chưa có rating (case 1) khi đang có phim demo | Không có phim nguồn `new` (phim mới chỉ dành cho tầng few/enough) | code |
| TC-18 | An chấm phim mới | Đi qua Kafka bình thường (không bị quarantine vì phim có trong danh mục), phim rời danh sách của An | đo |
| TC-19 | Tìm phim vừa thêm ở `/admin#/movies` và `/app` | Thấy ngay (nhãn "demo" ở admin), không đợi | code |
| TC-20 | Xoá phim demo | Có hộp thoại xác nhận trước; sau đó biến mất khỏi danh mục và gợi ý; rating đã có vẫn giữ, lịch sử hiện "Phim đã được gỡ khỏi danh mục" | đo |

**4. Danh sách phổ biến (WR)** (`/admin#/popularity`, tài khoản mới ở `/app`)
| ID | Làm gì | Kết quả mong đợi | Nguồn |
|---|---|---|---|
| TC-21 | Tạo tài khoản mới, xem 10 phim đầu | Shawshank, Godfather, Usual Suspects, Schindler's List, Godfather II… giống hệt bảng ở mục Phổ biến; mọi tài khoản mới nhận cùng danh sách | đo |
| TC-22 | Danh mục phim, tìm "planet earth" | Planet Earth (2006): 2,950 rating, điểm TB 4.463 nhưng WR **3.668**, thấp hơn ngưỡng top 10 (4.199) nên **không** lọt top 10 | đo |
| TC-23 | Cùng bảng, tìm "planet earth" | Planet Earth II (2016): có 1,956 rating nhưng điểm TB và WR là "—" (không có rating trong tập train, ra sau 10/2016) | đo |
| TC-24 | Mục Phổ biến, gõ `0` vào ô "Xem trước với m khác" | Planet Earth lên hạng 1 kèm dải "Đang xem trước"; danh sách tài khoản mới nhận **không đổi**; "Đặt lại" quay về | đo |
| TC-25 | Chấm một phim đang trong top 10 (ví dụ Shawshank), mở mục Phổ biến sau khi `applied` | Dòng "cộng N rating mới" tăng 1 và phim đó hiện "+n mới" ở cột số rating | đo |
| TC-26 | Danh mục phim, sắp theo "Điểm trung bình" giảm dần | Đầu bảng là các phim có **1 rating 5 sao** (điểm TB 5.0): lý do danh sách phổ biến dùng WR thay vì điểm TB thô | đo |

**5. Tìm kiếm** (`/admin#/movies` và `/app`)
| ID | Làm gì | Kết quả mong đợi | Nguồn |
|---|---|---|---|
| TC-27 | Tìm "pulp" | 4 phim: Pulp Fiction (1994), Pulp (1972), Pulp: a Film About Life, Death & Supermarkets (2014), Marvel: 75 Years, From Pulp to Pop! (2014); không phân biệt hoa thường | đo |
| TC-28 | Tìm "godfather part" | 2 phim: Part II và Part III (mọi từ phải có mặt) | đo |
| TC-29 | Lọc thể loại Western (không gõ tên) | Admin: 1,696 phim, 85 trang. `/app`: "Tìm thấy 1,696 phim, đang hiện 12" và nút "Xem thêm" | đo |
| TC-30 | Admin sắp theo số rating giảm dần | Shawshank (102,939), Forrest Gump (100,296), Pulp Fiction (98,425), The Matrix (93,808) | đo |
| TC-31 | `/app` gõ 1 ký tự | Không tìm; hiện "Nhập ít nhất 2 ký tự hoặc chọn một thể loại." | đo |
| TC-32 | Admin gõ tên không có thật ("zzzz") | "Không có phim nào khớp." (admin), "Không tìm thấy phim nào." (`/app`) | đo |

**6. Chịu lỗi** (cần một lệnh)
| ID | Làm gì | Kết quả mong đợi | Nguồn |
|---|---|---|---|
| TC-33 | `docker compose -f docker/docker-compose.yml stop streaming`, chấm sao ở `/app` | Rating được nhận (202) nhưng không áp dụng; trang chờ tối đa 60 giây rồi dừng chờ; sau `start streaming` rating vẫn được áp dụng | đo (đợt demo trước, `evidence/p2_demo_user_app.txt`) |
| TC-34 | `docker compose -f docker/docker-compose.yml stop kafka`, chấm sao ở `/app`, rồi `start kafka` | Thẻ "Đang gửi đánh giá…", sau khoảng 11 giây toast "Chưa lưu được đánh giá. Vui lòng thử lại." kèm nút **Thử lại**; sao được mở khoá. Streaming cần 1–2 phút để nối lại Kafka | đo (đợt demo trước) |

Ghi chú khi đọc kết quả: số **ratings** trong danh mục là tổng số rating (toàn bộ dữ liệu cộng rating mới), còn **Điểm TB và WR** tính trên tập train (đến 10/2016) cộng rating mới,
cùng nguồn với danh sách phổ biến, nên hai con số này có thể lệch nhau với phim ra sau 2016.

### Demo hai vai bằng hai tab (change `demo-user-app-personas`)

Có **hai trang** cho hai vai, mở ở hai tab cạnh nhau:

| Trang | Dành cho | Địa chỉ |
|---|---|---|
| **Ứng dụng người dùng** | khán giả: xem gợi ý, chấm sao, xem phim đã đánh giá, không có thuật ngữ kỹ thuật | http://127.0.0.1:8088/app |
| **Quản trị** (trang `/demo` cũ) | kỹ sư: case test, thêm/xoá phim, model và tiến độ retrain | http://127.0.0.1:8088/admin (vẫn mở được bằng `/demo`) |

Cả hai chỉ chạy khi `api.demo_enabled: true`. **Đây không phải đăng nhập thật**: các tài khoản là
persona demo gắn với người dùng MovieLens thật (đã ẩn danh), không có mật khẩu hay xác thực. Hãy nói
điều này khi thuyết trình. Persona chỉ mô tả bằng gu xem phim, không có tuổi hay giới tính.

| Persona | userId | Gu | Journey (PRD §4) |
|---|---|---|---|
| Tài khoản mới (tự tạo) | sinh mới | chưa có | A: phim phổ biến |
| **An** | 700008 | mới xem vài phim hình sự | B: gợi ý theo phim đã thích |
| **Bình** | 1 | khán giả lâu năm, chính kịch và tình cảm | C: có "Dành riêng cho bạn" (ALS) |
| **Chi** | 127249 | hài, phiêu lưu, viễn tưởng (không có ALS) | C hạ cấp, người dùng không thấy gì khác thường |

**Kịch bản 6 bước:**
1. Tab 1 mở `/app`, bấm **Tạo tài khoản mới**, nhập "Minh". Thấy phim phổ biến và lời mời "Hãy đánh giá vài phim bạn đã xem".
2. Chấm sao một phim. Thấy toast "Đã lưu đánh giá…", thẻ mờ đi với "Đang cập nhật gợi ý…". Khoảng 10–45 giây sau, gợi ý tự đổi sang "Giống phim bạn đã thích" và phim đó nằm trong "Phim bạn đã đánh giá".
3. Đăng xuất, chọn **Bình**: có nhãn "Dành riêng cho bạn" (ALS). Chọn **Chi**: danh sách bình thường dù không có ALS.
4. Mở tab 2 `/admin`, chọn case *3. Phim mới*, thêm phim "Phim hình sự mới" (Crime + Drama).
5. Chọn **An** ở tab 1 (hoặc quay lại tab của An): phim hiện ở hạng 3 với nhãn **Mới**, không cần bấm gì thêm.
6. Ở tab 2 xem case 5/6 để thấy phần Big Data phía sau (tiến độ retrain, model `v1.1.0` bị từ chối).

Ghi chú: cơ chế "tự làm mới khi quay lại tab" chỉ kích hoạt khi trình duyệt phát sự kiện đổi tab;
đã kiểm chứng logic bằng cách tự phát sự kiện (xem `evidence/p2_demo_user_app.txt` §5). Trang
người dùng không hiện `tier`, `strategy`, `fallbackReason`; muốn xem các thứ đó thì dùng `/admin`.
Dọn dẹp sau demo giống mục bên dưới (xoá phim demo).

### Demo theo case test (change `demo-use-case-scenarios`)

Ô **Case test** chứa bảng 9 use case nhóm chốt trong Doc "Notes - BDA501" (tab 5),
cộng thêm 2 case về serving. Mỗi case hiện thẻ 5 cột (*Điều gì xảy ra /
Recommendation / Streaming / ALS Retrain / Chốt*) đặt cạnh **tier và strategy quan
sát được** từ API, để người xem so kỳ vọng với thực tế.

**Chuẩn bị một lần** (stack chạy, streaming đang chạy):
```powershell
python scripts/seed_demo_users.py        # user 700008 có 3 rating (cho case 8, 2, 3, 4); chạy lại không gây hiệu ứng thêm
```
Nếu user 700008 đã bị rate nhiều lần và vượt ngưỡng T=10 thì chuyển sang
`enough_history`; tạo user mới bằng `--user-id 700009`.

| Case | Chọn gì | Bấm gì | Thấy gì |
|---|---|---|---|
| 1, 7 | *1. User có tài khoản, chưa rating* / *7. User mới* | — | user mới ngẫu nhiên, `0_history / POPULARITY` (case 7 = case 1 theo quyết định của nhóm) |
| 8 | *8. User mới bắt đầu rating* | — | user 700008, `few_history / CONTENT+POPULARITY` |
| 2 | *2. User có rating mới* | ⭐ một phim | 202 → `applied` → phim biến mất, `interaction_count` tăng |
| 3 | *3. Phim mới, chưa có rating* | nhập tên, tích Crime + Drama, **Thêm phim** | phim xuất hiện **hạng 3**, nhãn MỚI. Thêm một phim Western: không hiện vì user không có thể loại đó |
| 4 | *4. Phim mới bắt đầu có rating* | ⭐ lên phim MỚI | rating đi qua Kafka → streaming (không bị quarantine), phim biến mất khỏi gợi ý của user |
| 9 | *9. User mới + phim mới* | thêm phim Crime/Drama; rồi ⭐ một phim phổ biến cùng thể loại (ví dụ Shawshank) | trước khi rate: chỉ có danh sách phổ biến. Sau khi rate: `few_history` và phim mới xuất hiện hạng 3 |
| 5 | *5. Retraining* | — | thanh tiến độ: số event đã áp dụng kể từ lần bàn giao gần nhất / `n_min_events` (50) |
| 6 | *6. Model mới được promote* | — | bảng version: `v1.0.0` active, `v1.1.0` rejected kèm cổng G1–G3 không đạt |
| — | *Đã có rating và có ALS* / *Thiếu ALS* | — | `ALS+CONTENT` / fallback `als_artifact_missing` tô màu cam |

**Giải thích vì sao phim mới "được xếp hạng 3"** (câu hay bị hỏi): `similar_movies`
được tính sẵn, nên phim thêm sau không nằm trong danh sách của phim nào, đường
content không bao giờ đưa nó lên. Hệ thống dành riêng 1 vị trí (`new_items.position`
= 3, `new_items.slots` = 1 trong `configs/serving.yaml`) cho phim mới khớp thể loại
user hay xem. Cộng thêm điểm vào RRF không đủ: phim đứng cuối trong doc ALS của
user vẫn có điểm cao hơn phim mới trừ khi trọng số ≥ 0.87, mà khi đó phim mới lại
đè lên cả phim ALS tốt nhất. Tier `0_history` không nhận phim mới (nhóm chốt case 1
dùng popularity); user mới chỉ nối được với phim mới sau rating đầu tiên.

**Case 5/6 chỉ để xem**: trang không có nút kích hoạt retrain hay promote, vì việc
train chạy trên Colab của Person 1. "Lịch chốt 1 tuần" hiện là thiết kế, chưa có
scheduler chạy thật (`interval_minutes: null`; trigger theo số event hoặc `--force`).

**Dọn dẹp sau khi demo, và BẮT BUỘC trước khi chạy lại `bootstrap_registry`**:
phim demo nằm trong collection `movies`, còn `bootstrap_registry` kiểm tra số phim
đúng bằng 87,585. Xoá bằng nút **Xoá** trên trang (case 3/4/9), hoặc:
```powershell
curl -X DELETE http://127.0.0.1:8088/movies/<movieId>      # chỉ nhận id >= 9,000,000, MovieLens bị từ chối (404)
```
Xoá phim **không** xoá rating đã gán cho nó (`user_rated` và `curated_ratings` vẫn
giữ). Id phim demo không bao giờ được cấp lại, nên rating cũ không dính sang phim
mới. Phim demo chỉ nằm trong MongoDB, không vào `curated_movies`: xem
`docs/DEPLOYMENT_DESIGN.md` §2.8.

---

## 3. Flow test A — 3 tier gợi ý (nhanh nhất, chỉ cần API)

```powershell
# Tier "chưa có lịch sử" — dùng userId chưa từng tồn tại
curl http://127.0.0.1:8088/recommendations/999888777?k=5
# Kỳ vọng: tier=0_history, strategy=POPULARITY

# Tier "đủ lịch sử, có ALS" — userId=1 luôn có sẵn trong data mẫu
curl http://127.0.0.1:8088/recommendations/1?k=5
# Kỳ vọng: tier=enough_history, strategy=ALS+CONTENT, fallbackReason=null

# Tier "đủ lịch sử nhưng KHÔNG có ALS" (nhóm 46,340 user cold-start)
curl http://127.0.0.1:8088/recommendations/127249?k=5
# Kỳ vọng: tier=enough_history, strategy=CONTENT+POPULARITY, fallbackReason=als_artifact_missing
```

**Test validate input (phải trả lỗi 422, không phải 500):**
```powershell
curl -i http://127.0.0.1:8088/recommendations/1?k=0      # k quá nhỏ
curl -i http://127.0.0.1:8088/recommendations/1?k=51     # k quá lớn
curl -i http://127.0.0.1:8088/recommendations/-5         # userId âm
```

---

## 4. Flow test B — rating mới qua Kafka đổi gợi ý ngay lập tức

**Bước 1 — chọn 1 userId mới, gọi API xem tier hiện tại:**
```powershell
curl http://127.0.0.1:8088/recommendations/400001?k=5
# tier=0_history
```

**Bước 2 — cần streaming pipeline đang chạy.** Pipeline là service `streaming`,
kiểm tra:
```powershell
docker compose -f docker/docker-compose.yml ps streaming
```
Phải `Up ... (healthy)`. Nếu không, bật bằng `docker compose -f
docker/docker-compose.yml up -d streaming` (không còn cần cửa sổ terminal riêng).

**Bước 3 — quay lại cửa sổ chính, gửi 3 rating cho user đó:**
```powershell
docker compose -f docker/docker-compose.yml exec spark python -m streaming.producer `
  --mode scenario --user-id 400001 --movie-ids 296,318,858 --bootstrap-servers kafka:9092
```

**Bước 4 — đợi khoảng 15–45 giây (độ trễ đã đo, xem mục 2b), gọi lại API:**
```powershell
curl http://127.0.0.1:8088/recommendations/400001?k=5
# Kỳ vọng: tier=few_history (đổi từ 0_history), strategy=CONTENT+POPULARITY
```

---

## 5. Flow test C — loại phim vừa xem (fresh-history exclusion)

```powershell
# 1. Xem top gợi ý ALS hiện tại của userId=1
curl http://127.0.0.1:8088/recommendations/1?k=3
# Ghi lại movieId đầu tiên trong danh sách, ví dụ 60376

# 2. Giả lập user vừa rate CHÍNH phim đó (thay 60376 bằng movieId bạn vừa ghi)
docker compose -f docker/docker-compose.yml exec spark python -c "
import time, uuid, json
from confluent_kafka import Producer
p = Producer({'bootstrap.servers':'kafka:9092','acks':'all','enable.idempotence':True})
ev = {'eventId': str(uuid.uuid4()), 'userId': 1, 'movieId': 60376, 'rating': 5.0, 'timestamp': int(time.time()), 'source':'manual-test'}
p.produce('ratings.v1', key='1', value=json.dumps(ev).encode()); p.flush(10)
print('sent', ev)
"

# 3. Đợi ~10 giây, gọi lại API — movieId đó PHẢI biến mất khỏi danh sách
curl http://127.0.0.1:8088/recommendations/1?k=5
```

---

## 6. Flow test D — event không hợp lệ bị chặn đúng cách

```powershell
docker compose -f docker/docker-compose.yml exec spark python -m streaming.producer `
  --mode invalid --user-id 1 --movie-ids 296,318,858 --bootstrap-servers kafka:9092
```
Gửi 6 event cố tình sai (rating=7.0, userId=0, phim không tồn tại, timestamp
sai...). Kiểm tra chúng bị cách ly, không lọt vào dữ liệu chính:
```powershell
docker compose -f docker/docker-compose.yml exec spark python -c "
from pyspark.sql import SparkSession
spark = SparkSession.builder.appName('check').master('local[*]').getOrCreate()
spark.sparkContext.setLogLevel('ERROR')
spark.read.parquet('/data/stream/quarantine').select('eventId','reason').show(20, truncate=False)
"
```

---

## 7. Flow test E — gửi trùng 1 event (idempotency)

```powershell
docker compose -f docker/docker-compose.yml exec spark python -m streaming.producer `
  --mode duplicate --user-id 1 --movie-ids 296 --n 3
```
Gửi 3 lần **cùng 1 eventId**. Kiểm tra ledger chỉ có đúng 1 bản ghi:
```powershell
docker compose -f docker/docker-compose.yml exec spark python -c "
from pymongo import MongoClient
db = MongoClient('mongodb://mongo:27017')['movielens']
print('tổng ledger:', db.rating_events.count_documents({}))
"
```

---

## 8. Flow test F — chạy toàn bộ script demo tự động (gộp mục 3–5–7)

Không cần làm tay từng bước — script này tự chạy hết và tự kiểm tra kết quả:
```powershell
python -m venv .venv-serving
.venv-serving\Scripts\pip install -r configs/requirements_serving.txt
.venv-serving\Scripts\python scripts/demo_e2e.py --user-id 300200 --api http://127.0.0.1:8088
```
Kỳ vọng: in ra `DEMO COMPLETE - all assertions passed` ở cuối. Đổi `--user-id`
thành số khác mỗi lần chạy lại (script tự cảnh báo nếu dùng lại userId đã có
lịch sử).

---

## 9. Flow test G — retrain / promotion gate (chỉ chạy được khi có candidate)

**⚠️ Hiện đang BLOCKED**: 2 file trong model `als_v1.0.0` trên Drive (Quyên) bị
lỗi 0 byte, đã báo và đang chờ sửa. Chạy được phần trigger + stage, nhưng gate
sẽ FAIL ở bước tính RMSE (đã verify: FAIL đúng cách, không crash, không đổi
version đang chạy).

```powershell
# Đếm event mới, ép tạo gói bàn giao dù chưa đủ ngưỡng
docker compose -f docker/docker-compose.yml exec spark python -m orchestration.retrain_trigger --force

# Kiểm tra: model đang phục vụ KHÔNG đổi (luôn đúng dù gate PASS hay FAIL)
docker compose -f docker/docker-compose.yml exec spark python -c "
from pymongo import MongoClient
db = MongoClient('mongodb://mongo:27017')['movielens']
print(db.serving_meta.find_one({'_id':'active'}))
"
```

---

## 9b. Flow test H — mất checkpoint của streaming (đường lỗi)

Kiểm tra rằng mất thư mục checkpoint trong khi Mongo còn nguyên **không** làm rating mới bị bỏ qua
(`address-person1-review-findings` D-2). Chỉ làm trên môi trường demo.

```powershell
docker compose -f docker/docker-compose.yml stop streaming
Move-Item movielens32m\stream\checkpoints\valid movielens32m\stream\checkpoints\valid.bak
docker compose -f docker/docker-compose.yml start streaming
docker compose -f docker/docker-compose.yml logs --since 2m streaming
```

Kỳ vọng trong log (sau khoảng 30–60 giây):
- `serve_batch[0]: WARNING checkpoint changed (recorded <id cũ>, running <id mới>): lastBatchId=N no longer applies`
- `serve_batch[0]: 4x row(s), 0 new after ledger dedup`: phát lại toàn bộ `raw_events` không ghi thêm gì (ledger dedup).

Rồi gửi một rating bằng `/app` hoặc `POST /ratings`: `GET /ratings/{eventId}` phải thành `applied` sau 12–45 giây.
Xong thì xoá `valid.bak`. Với code trước khi sửa, rating này kẹt `pending`, log ghi
`already committed (last=N), skipping`, và batch kế tiếp làm query chết vì thiếu file `.delta` (xem
`evidence/p2_review_fixes.txt` mục 3).

## 9c. Flow test I — handoff khi streaming đang ghi (đường lỗi)

`retrain_trigger` chỉ xuất event của batch **đã commit** (`ingestedAt` trong `(watermark, lastRunAt]`) và
đặt watermark mới bằng đúng cận trên đó, nên một batch đang ghi dở không bị cắt đôi hay rơi khỏi cả hai gói
(`address-person1-review-findings` D-1). Logic có unit test (`tests/unit/test_handoff_window.py`); kịch bản chạy
thật (đặt `lastRunAt`, chèn hai event ledger tổng hợp trước và sau `lastRunAt`, chạy `retrain_trigger --force` hai lần)
và kết quả đo nằm ở `evidence/p2_review_fixes.txt` mục 2. Kịch bản đó sửa `pipeline_state` và `rating_events`,
nên **phải khôi phục** chúng sau khi thử.

---

## 10. Nếu có lỗi

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
|---|---|---|
| `curl` không kết nối được cổng 8088 | Container `api` chưa healthy, hoặc port 8000 đang bị app khác chiếm (đã đổi sang 8088 vì lý do này) | `docker compose -f docker/docker-compose.yml ps` xem status |
| API trả `503` | Chưa nạp dữ liệu / chưa activate version nào | Chạy lại bước nạp Mongo trong README mục 2 |
| `docker compose exec` báo "no such service" | Đứng sai thư mục | Phải đứng ở gốc repo khi chạy lệnh |
| Streaming không thấy đổi gì sau khi gửi event | Service `streaming` đang dừng, đang khởi động lại (mất 1–2 phút), hoặc đang chậm vì có job Spark khác chạy song song | `docker compose -f docker/docker-compose.yml ps streaming`; xem log bằng `logs -f streaming`; nếu `exited` thì `up -d streaming` |
| Docker Desktop tự tắt (đã gặp 3 lần) | WSL2/Docker Desktop trên Windows đôi khi tự dừng khi máy sleep | Mở lại Docker Desktop: các service (kể cả `streaming`) tự chạy lại nhờ `restart: unless-stopped`, dữ liệu không mất. Đợi 1–2 phút rồi mới thử |
