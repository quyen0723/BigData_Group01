# Ghi chú bàn giao Person 1 (Quyên) — từ phần serving/demo

Gửi nguyên văn hoặc rút gọn tuỳ ý. Có 3 việc, theo thứ tự quan trọng với buổi demo M8 (03/10).

## 1. Popularity theo weighted rating (Bayesian / kiểu IMDb) — việc của Quyên

Trong Doc "Notes - BDA501" (case 1) nhóm chốt popularity nên dùng weighted rating. Hiện
`popular_movies.json` đang xếp theo **điểm trung bình thô**, chỉ lọc `min_support = 100`
(MODEL_DESIGN.md §3). Phần serving chỉ đọc file này, nên cần Quyên xuất lại.

**Công thức** (mỗi phim có sẵn `m` rating "bình thường" bằng điểm trung bình chung `C`):

```
WR = v/(v+m) · R  +  m/(v+m) · C
R = điểm trung bình của phim    v = số rating của phim
C = điểm trung bình toàn tập (MODEL_DESIGN.md ghi 3.5287)    m = ngưỡng tin cậy, cần chọn
```

Phim ít rating bị kéo về gần `C`, phim nhiều rating giữ điểm thật. Không phim nào bị loại hẳn
như với `min_support`.

**Vì sao đáng làm** — số thật từ artifact đang chạy (R, v) và WR tính từ công thức trên:

| Phim | R (thô) | v | WR (m=100) | WR (m=1000) | WR (m=5000) |
|---|---|---|---|---|---|
| Planet Earth (2006) — hạng 1 hiện tại | 4.468 | 173 | 4.124 | 3.667 | 3.560 |
| The Blue Planet (2001) — hạng 3 | 4.345 | 132 | 3.993 | 3.624 | 3.550 |
| Shawshank Redemption — hạng 2 | 4.428 | 73,945 | 4.427 | 4.416 | 4.371 |
| Godfather, The — hạng 4 | 4.344 | 47,709 | 4.342 | 4.327 | 4.267 |

Với `m ≥ 1000`, Shawshank lên hạng 1 và hai phim tài liệu ít rating tụt khỏi top.

**Quyên cần quyết định / làm:**
1. Chọn `m` (cố định, hay theo phân vị số rating, ví dụ top 10% số rating của phim). Chỉ có số
   của 4 phim ở trên; top-10 đầy đủ cần tính trên toàn bộ `curated_ratings` (phía Quyên có sẵn).
2. Có giữ `min_support = 100` song song không.
3. Tính trên tập train hay toàn bộ (MODEL_DESIGN.md hiện dùng split theo thời gian).
4. Xuất lại `popular_movies.json` **giữ nguyên cấu trúc hợp đồng** (CONTRACTS.md §3.1:
   `scope`, `modelVersion`, `generatedAt`, `items[] {movieId, title, genres, rank, score, support}`),
   với `score` = WR. Bản mới là một version mới (ví dụ `v1.2.0`), đi qua đường nhập candidate
   + promotion gate như thường lệ, không ghi đè `v1.0.0`.

## 2. Phim demo trong `curated_ratings` — cần biết, chưa cần làm gì ngay

Trang demo có chức năng "Thêm phim mới" (cho case 3, 4, 9 trong bảng use case). Phim này chỉ nằm
trong MongoDB, **không** vào `curated_movies`. Nhưng rating cho phim đó vẫn được streaming
append vào `curated_ratings` như mọi rating. Nên `curated_ratings` có thể chứa
`movieId ≥ 9,000,000` không có trong `curated_movies`.

Khi retrain, job cần **bỏ qua hoặc chấp nhận** các `movieId` này (ví dụ lọc
`movieId < 9000000`), kẻo join với `curated_movies` ra null hoặc ALS học thêm item lạ. Hiện đã có
một vài dòng như vậy từ lần test (movieId 9000000, vài user).

## 3. Nhắc lại việc còn treo từ trước

Hai file của model `als_v1.0.0` vẫn **0 byte** (kiểm tra ngày 01/10):
`models/als_v1.0.0/userFactors/part-00000-…parquet` và `part-00001-…parquet`
(8 file còn lại ~3 MB mỗi file). Hậu quả: promotion gate không tính được RMSE (G1–G3 FAIL), nên
chưa chứng minh được nhánh PASS. Trang demo (case 6) đang hiển thị đúng điều này cho `v1.1.0`.
Cần Quyên tải lại model từ Colab lên Drive (đã hỏi từ trước, chưa thấy sửa).
