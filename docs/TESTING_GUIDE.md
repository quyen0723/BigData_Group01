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
`GET /admin`, `GET /users/{userId}/ratings`.

---

## 2b. Demo bằng giao diện (khuyên dùng cho buổi thuyết trình)

Đây là cách nhanh nhất để giám khảo **thấy** hệ thống hoạt động mà không cần
nhìn lệnh terminal: 1 trang HTML tĩnh, tự phục vụ bởi chính API, không cần cài
gì thêm, không cần internet.

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

## 10. Nếu có lỗi

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
|---|---|---|
| `curl` không kết nối được cổng 8088 | Container `api` chưa healthy, hoặc port 8000 đang bị app khác chiếm (đã đổi sang 8088 vì lý do này) | `docker compose -f docker/docker-compose.yml ps` xem status |
| API trả `503` | Chưa nạp dữ liệu / chưa activate version nào | Chạy lại bước nạp Mongo trong README mục 2 |
| `docker compose exec` báo "no such service" | Đứng sai thư mục | Phải đứng ở gốc repo khi chạy lệnh |
| Streaming không thấy đổi gì sau khi gửi event | Service `streaming` đang dừng, đang khởi động lại (mất 1–2 phút), hoặc đang chậm vì có job Spark khác chạy song song | `docker compose -f docker/docker-compose.yml ps streaming`; xem log bằng `logs -f streaming`; nếu `exited` thì `up -d streaming` |
| Docker Desktop tự tắt (đã gặp 3 lần) | WSL2/Docker Desktop trên Windows đôi khi tự dừng khi máy sleep | Mở lại Docker Desktop: các service (kể cả `streaming`) tự chạy lại nhờ `restart: unless-stopped`, dữ liệu không mất. Đợi 1–2 phút rồi mới thử |
