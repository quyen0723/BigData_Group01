## Context

Hôm nay danh sách phổ biến đi một đường một chiều và tĩnh:

```
split_baselines.py (Quyên, offline, 32M rating)        popular_movies.json (10 phim, score = WR)
  train 70% theo thời gian, C = 3.5287, m = 1000   ──►  loaders/load_artifacts ──► Mongo popular_movies
                                                                                      │
                                      GET /recommendations ◄── service.py ◄───────────┘   (chỉ đọc)
```

Streaming ghi mỗi rating mới vào `curated_ratings` (parquet, append), `user_rated`, `user_history`, rồi **cuối cùng** vào ledger `rating_events` (`pipeline.py` bước 6: "in ledger" nghĩa là "đã áp dụng"). Không có gì trong đó chạm tới danh sách phổ biến.

Ràng buộc đã kiểm:
- Mongo chạy bản đơn lẻ (`docker-compose.yml`, không có `--replSet`), nên **không có transaction nhiều tài liệu**.
- Ledger có `_id = eventId`, `userId`, `movieId`, `rating`, `timestamp`, `batchId`, `ingestedAt`; chèn có khoá duy nhất nên một eventId chỉ vào một lần.
- Cutoff của tập train nằm trong `evidence/split_stats.csv`: `cut_val = 1476348398`, `n_train = 22,399,368`; `C = 3.5287` trong `evidence/b3_1_split_baseline.txt`. Container `spark` mount `evidence/` tại `/app/evidence` và dữ liệu tại `/data`.
- `service.get_recommendations` lấy danh sách phổ biến ở một chỗ duy nhất (`repo.get_popular_movies`, `service.py:105`) rồi dùng làm nguồn tier 0, phần đệm và nguồn thứ hai của tier few.

## Goals / Non-Goals

**Goals**
- Chấm rating thì danh sách phổ biến (tier 0) đổi theo WR **trong vài giây sau `applied`**, với đúng công thức, tham số và thứ tự của bản offline.
- Trình bày được bằng chứng đo: bảng top 10 có điểm TB, số rating, WR; đổi hạng thật ở cặp hạng 8–9 với khoảng 18 rating; phim ít người chấm bị kéo về trung bình.
- Không sửa streaming, không đổi schema ledger, không đổi hành vi nào khác của API; tắt bằng một cờ.

**Non-Goals**
- Bộ đếm do streaming cập nhật (cần idempotency chặt hơn; hướng mở rộng khi ledger lớn).
- Đổi `m` hay `C` trên hệ thống đang chạy (chỉ xem trước), thống kê theo thể loại, giải thích gợi ý.
- Làm popularity theo thời gian (cửa sổ trượt), cá nhân hoá.

## Decisions

### D-1. Delta lấy từ ledger, không sửa streaming
WR sống của phim = baseline (train) + các rating đã áp dụng. Các rating đã áp dụng **chính là ledger**. Hai hướng đã cân:

| | Delta từ ledger (chọn) | Bộ đếm `$inc` trong `serve_batch` |
|---|---|---|
| Đúng đúng một lần | Có sẵn (ledger chỉ chèn một lần theo eventId) | Không: crash giữa `$inc` và ghi ledger thì replay đếm dư (hoặc thiếu nếu đổi thứ tự); không có transaction trên Mongo đơn lẻ |
| Đụng streaming | Không | Có (phần mong manh nhất, vừa sửa nhiều lỗi) |
| Chi phí đọc | Quét ledger mỗi lần làm mới (cache) | O(1) |
| Quy mô | Tốt đến hàng chục nghìn event | Tốt hơn |

Chọn ledger vì rủi ro thấp và đúng ở quy mô demo; ghi rõ giới hạn quy mô và hướng nâng cấp ở Risks.

Delta tính bằng một pipeline Mongo: (tuỳ chọn `$match ingestedAt > ledgerSince`) → `$sort timestamp, ingestedAt` → `$group` theo (userId, movieId) lấy `$last rating` → `$group` theo movieId (`n` = số cặp, `sum` = tổng điểm), `allowDiskUse`.

### D-2. Lưu `n0` và `sum0`, không lưu WR
`movie_stats{_id: movieId, n0, sum0}` (36,526 tài liệu đo trên dữ liệu thật; chỉ phim có rating trước cutoff) và một tài liệu `_id: "_meta"` ghi `C`, `cutoff`, `ratings`, `movies`, `generatedAt`, `ledgerSince` (null lúc đầu). Lưu số thô thay vì WR để (a) tính được với `m` bất kỳ (xem trước) và (b) tính lại điểm TB `R = sum/n` cho bảng giải thích. Người đọc phải bỏ qua `_meta` (id không phải số).

### D-3. Baseline lấy từ tập train, đúng cutoff của Quyên
Loader `build_movie_stats.py` đọc `curated_ratings`, lọc `timestamp < cut_val` (đọc từ `evidence/split_stats.csv`, có thể ghi đè bằng `--cutoff`), gộp theo `movieId`. Hai cổng kiểm làm loader **thất bại** nếu sai: tổng số rating phải bằng `n_train` trong file, và điểm TB toàn cục phải bằng `C` đã ghi (4 chữ số). Cách này chặn việc vô tình lẫn rating streaming (timestamp 2026 nên bị cutoff loại) hay dữ liệu val/test (rò rỉ). Lý do không dùng toàn bộ 32M: khớp với artifact của Quyên nên so sánh được (D-12), `C` là hằng số train-only như cô ấy định nghĩa. Ghi bằng cùng helper `write_collection(..., operation_type="replace")` như `build_movies.py`; tài liệu meta ghi bằng pymongo sau cùng.

### D-4. Công thức, thứ tự và lọc giống bản offline
`WR = v/(v+m)·R + m/(v+m)·C`, với `v = n0 + n_mới`, `R = (sum0 + sum_mới)/v`. Thứ tự **WR giảm, rồi v giảm, rồi movieId tăng**. Lọc `v ≥ min_support` (100) trên `v` hiện tại. WR giữ độ chính xác đầy đủ (artifact làm tròn 3 chữ số, nên so sánh dùng dung sai 5×10⁻⁴). `top_n` mặc định 10 để tier 0 và phần đệm giữ nguyên kích thước như hôm nay. Mỗi phần tử trả cho `service` có `score = WR`, `support = v` đúng hợp đồng cũ.

### D-5. Tính trong API, baseline nằm trong bộ nhớ
Baseline nạp một lần (và nạp lại khi `generatedAt` của meta đổi). Mỗi lần làm mới: chạy pipeline delta, tính WR cho toàn bộ phim đủ điều kiện, lấy top-N bằng `heapq.nlargest`. Việc đắt nhất là quét ledger và nó không phụ thuộc `m` hay `n`, nên kết quả quét được cache riêng theo `ledgerSince` trong `cache_ttl_seconds` (mặc định 2) và dùng chung cho mọi tổ hợp; bảng xếp hạng (rẻ, khoảng 20 ms) cache theo (`m`, có/không delta, `n`), tối đa 32 khoá và không bao giờ đuổi khoá mà `/recommendations` đang đọc. Một khoá làm mới tại một thời điểm; người đọc đã có kết quả gần đây thì nhận luôn kết quả đó thay vì chờ (không xếp hàng sau lần quét ~1 giây khi ledger lớn), người chưa có thì chờ rồi dùng kết quả mới. Kết quả rỗng (không phim nào đủ `min_support`) được coi như không có baseline: dùng artifact và cảnh báo, vì danh sách rỗng sẽ để user mới không có gợi ý nào. Ngân sách: làm mới ≤ 100 ms (đo: 24 ms với 36,5 nghìn phim và ledger hiện có; 14–25 ms cho 80 nghìn phim giả lập). Nếu chậm hơn thì tối ưu bằng cách chỉ tính lại phim có delta trên thứ tự baseline đã sắp.

### D-6. Đường lùi, không để request gợi ý thất bại
Thứ tự: cờ `popularity.live` tắt → artifact. Thiếu baseline (`movie_stats` rỗng hoặc không có `_meta`) → artifact + một cảnh báo. Lỗi khi đọc ledger hoặc Mongo → dùng kết quả tốt gần nhất nếu không quá 60 giây, nếu không thì artifact; cảnh báo tối đa một lần mỗi phút cho mỗi nguyên nhân. `GET /debug/popularity` cho biết nguồn đang dùng (`live` hay `artifact`).

### D-7. Mỗi cặp (user, phim) chỉ đếm một lần, lấy rating mới nhất
Giống `user_rated` (latest-timestamp-wins). Giới hạn đã biết: nếu một event nhắm vào cặp đã có trong train thì nó được đếm **thêm** (không biết giá trị cũ để thay). UI không cho chấm lại phim đã chấm nên chỉ event viết tay mới gặp; ghi vào docs.

### D-8. `ledgerSince` tránh đếm đôi khi baseline được dựng lại
Hôm nay baseline là train 2016 nên `ledgerSince = null` (đếm mọi event trong ledger). Nếu sau này dựng lại baseline từ dữ liệu đã chứa các event streaming (sau một lần retrain), loader nhận `--ledger-since <thời điểm>` và API chỉ đếm event có `ingestedAt` sau mốc đó. Chỉ cần tham số và test, không cần chạy lại bây giờ.

### D-9. Endpoint `GET /debug/popularity`
Demo-only (404 khi `api.demo_enabled` tắt, giống các route debug khác). Tham số: `n` (1–50, mặc định 10), `m` (0–100000, mặc định giá trị cấu hình; khác thì `preview: true`), `deltas` (mặc định true; false = baseline thuần, dùng để so với artifact). Chạy được cả khi `popularity.live` còn tắt (cần cho bước kiểm tra trước khi bật cờ); `liveEnabled` nói `/recommendations` có đang dùng danh sách sống không. Trả `{source, liveEnabled, preview, m, c, minSupport, baseline: {generatedAt, cutoff, ratings} | null, appliedEvents, generatedAt, items: [{rank, movieId, title, genres, avgRating, support, baseSupport, newRatings, wr, baseRank}]}`. `baseRank` là hạng của phim trong thứ tự baseline cùng `m` (null nếu ngoài top 200). Khi `source = artifact` thì `avgRating = null`, `newRatings = 0`. Sai tham số trả 422.

### D-10. Mục admin "Phổ biến" (`#/popularity`)
Bảng top 10 với cột: hạng, phim, điểm TB (R), số rating (v, kèm "+n mới"), WR, thay đổi hạng so với baseline. Tự làm mới 3 giây **chỉ khi tab đang hiện và mục đang mở** (TanStack Query `refetchInterval`, không chạy nền). Phim đổi hạng được đánh dấu bằng mũi tên và chữ ("lên 1", "xuống 1") chứ không chỉ bằng màu; hiệu ứng sáng ngắn tôn trọng `prefers-reduced-motion`. Chọn một dòng mở khung **công thức từng bước**: thay số vào `v/(v+m)·R + m/(v+m)·C` và nói trọng số `w = v/(v+m)` bằng lời ("phim này được tin 93% điểm riêng của nó, 7% kéo về trung bình chung"). Ô nhập `m` có nhãn "Xem trước, không đổi hệ thống" và một dải thông báo khi đang xem trước. Dùng lại token màu, bảng, skeleton của design system hiện có, thêm vào sidebar và route.

### D-11. Script demo `scripts/wr_live_demo.py` (chỉ dùng thư viện chuẩn)
- `check`: so `GET /debug/popularity?deltas=false&m=<m cấu hình>` với `artifacts/popular_movies.json` (đúng thứ tự movieId, WR chênh ≤ 5×10⁻⁴). Đây là bằng chứng "sống = offline khi chưa có event".
- `plan`: lấy top 12, với từng cặp liền kề tính số rating 5 sao cần để phim dưới vượt phim trên (dùng R và v **chính xác** từ API), in bảng và gợi ý cặp gần nhất.
- `inject --movie ID --stars S --n N`: tạo N user giả trong dải 999200001 trở đi, bỏ qua user đã có lịch sử; eventId là `uuid5(namespace, "wr-live-demo:<user>:<movie>")` nên chạy lại là idempotent; gửi `POST /ratings`, thử lại cùng eventId khi 503; chờ `applied` (hạn chờ theo `ratingPollTimeoutSeconds` + N × 0.2 giây); in bảng trước và sau với thay đổi hạng.
- `spam --movie ID`: như `inject` nhưng theo mốc 10, 100 và số rating cần để vượt ngưỡng top 10, in WR ở từng mốc (chống chịu chứ không miễn nhiễm).
- `--dry-run` cho mọi lệnh gửi.

### D-12. Dọn dữ liệu giả
User giả (dải 999,000,000–999,999,999, gồm 999100001–999100010 đã có) nằm ở bốn nơi: ledger `rating_events`, `user_rated`, `user_history` (Mongo) và `curated_ratings` (parquet, phân vùng `year=2026`). `scripts/purge_demo_ratings.py` xoá ba nơi đầu, mặc định `--dry-run`, từ chối dải ngoài 999M–999.99M, in số bản ghi. Parquet: thủ tục lọc và ghi lại phân vùng `year=2026` được viết vào TESTING_GUIDE và chạy thử một lần trên bản sao, chỉ thực hiện thật khi người dùng yêu cầu. **Phải dọn ledger trước mỗi lần bàn giao retrain**, vì `retrain_trigger` xuất event từ ledger.

### D-13. Kiểm chứng
- Thuần: so `popularity.py` với tính brute force trên dữ liệu ngẫu nhiên (thứ tự, tie-break, lọc support, `m = 0` ra điểm TB thô, `v → ∞` thì WR → R).
- Repository (fake): delta gộp theo cặp, theo `ledgerSince`; eventId trùng không nằm trong ledger hai lần (đã đảm bảo bởi `_id`).
- API: tier 0 dùng danh sách sống; tắt cờ, thiếu baseline, lỗi ledger đều rơi về artifact và request vẫn 200; endpoint debug (gate, tham số, 422).
- Trên stack thật: `check` đạt; đo độ trễ làm mới; chạy `plan` rồi `inject` 20 rating vào hạng 9 và thấy đổi hạng 8–9 trên bảng admin; `spam` 100 rating không vào top; tắt cờ và lùi về artifact; dọn dữ liệu giả; không phát sinh lỗi trong log `streaming`.

## Risks / Trade-offs

- **[Quét ledger tăng theo số event]** → cache TTL, `allowDiskUse`, đo ở 8.2; ghi rõ giới hạn và hướng bộ đếm. Có thể thêm chỉ mục `rating_events(ingestedAt)` nếu cần.
- **[Rating giả vào ledger, `user_rated`, parquet]** → dải userId riêng, script dọn, cảnh báo bàn giao retrain trong TESTING_GUIDE. Parquet vẫn là việc thủ công có kiểm soát.
- **[Lệch với artifact của Quyên]** nếu cô ấy đổi `m`, `C`, `min_support` hay cutoff → `check` bắt được; baseline và cấu hình phải cập nhật cùng nhau; thông báo cho Quyên rằng `popular_movies.json` mới sẽ không có tác dụng ở chế độ sống nếu không dựng lại baseline.
- **[Đổi hành vi tier 0]** danh sách giờ thay đổi theo rating → có cờ `popularity.live`; mặc định trong code là `false`, giá trị trong `configs/serving.yaml` chỉ bật sau khi qua 8.x (cùng cách với `api.ui`).
- **[Loader Spark nặng]** quét 32M dòng → chạy một lần lúc chuẩn bị, không chạy khi đang demo (tranh CPU với `streaming`).
- **[Hạn chế đã biết]** event nhắm vào cặp đã có trong train được đếm thêm (D-7); WR chống chịu chứ không miễn nhiễm trước spam đủ lớn (cỡ 780 rating 5 sao với Planet Earth).

## Migration Plan

1. Thêm code với `popularity.live` mặc định tắt: không đổi hành vi nào.
2. Chạy `build_movie_stats` (vài phút, không ảnh hưởng người dùng) và `check`.
3. Bật `popularity.live: true` trong `configs/serving.yaml`, restart `api`; xác nhận tier 0 và `GET /debug/popularity`.
4. Rollback: đặt `live: false`, restart `api`. `movie_stats` có thể để nguyên.

## Open Questions

- Baseline từ tập train (đề xuất, khớp artifact) hay toàn bộ rating? Đề xuất train; đổi sang toàn bộ chỉ là đổi cutoff và mất phép so với artifact.
- Có bật `live: true` trong cấu hình được commit không? Đề xuất có, sau khi qua kiểm chứng.
- Parquet: dọn thật ngay sau buổi demo hay chấp nhận tới lần retrain kế tiếp? Cần ý kiến của Quyên vì cô ấy là người nhận gói retrain.
