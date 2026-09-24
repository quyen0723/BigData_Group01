# Hướng dẫn chạy trên Google Colab — Person 1 (Phase 3: B3.1 → B3.5)

> Mục tiêu: train model (split, baselines, content-based, ALS, evaluation) trên Colab
> vì máy local thiếu RAM cho ALS full 32M. Input duy nhất cần upload: **curated Parquet**.

## Bước 0 — Chuẩn bị file upload (trên máy local, 1 lần)

Curated data đã có ở `data/curated/` (từ B1.3, ~506MB). Nén lại để upload:

```bash
cd /home/fong/Projects/big_data/final_project
zip -r data/curated.zip data/curated
# Kết quả mong đợi: data/curated.zip ≈ 300-500MB (parquet nén sẵn)
```

**KHÔNG cần upload `ml-32m.zip`** — notebook Colab đọc trực tiếp curated parquet,
không chạy lại ETL (đã verify PASS local ở B1.3, evidence `b1_3_curated.txt`).

## Bước 1 — Upload lên Google Drive

1. Mở [drive.google.com](https://drive.google.com) → tạo thư mục **`movielens32m`** ở My Drive.
2. Upload `curated.zip` vào thư mục đó.
3. (Drive upload >200MB có thể chậm/cần xác nhận — chờ upload xong 100% mới mở Colab.)

Cấu trúc Drive sau khi notebook chạy xong:

```
MyDrive/movielens32m/
├── curated.zip          ← bạn upload (Bước 1)
├── curated/             ← notebook 01 tự unzip
├── artifacts/           ← OUTPUT: popular_movies.json, similar_movies.json, als_topn.json,
│                          user_history.parquet, model_card.json
├── evidence/            ← OUTPUT: split_stats.csv, metrics.csv, als_grid_search.csv, ...
├── models/als_v1.0.0/   ← OUTPUT: ALS model saved (Spark ML format — cho B6 retrain gate)
└── checkpoints/         ← ALS checkpoint dir (MANDATORY, tự tạo)
```

## Bước 2 — Mở Colab

1. Vào [colab.research.google.com](https://colab.research.google.com) → **File → Upload notebook**
   → chọn `notebooks/colab/01_split_baseline.ipynb` từ repo.
2. **Runtime → Change runtime type → High-RAM** (nếu account có; không có thì dùng
   default ~12.7GB — vẫn OK vì đã có checkpoint dir + driver memory 8g + fallback).
3. **Runtime → Run all**. Cell đầu sẽ mount Drive (cần authorize Google account).

## Bước 3 — Chạy theo thứ tự (BẮT BUỘC)

| Thứ tự | Notebook | WBS | Output | Thời gian ước tính |
|--------|----------|-----|--------|--------------------|
| 1 | `01_split_baseline.ipynb` | 3.1 + 3.2 | split_stats.csv, metrics_partial.csv, popular_movies.json | ~15-20 phút |
| 2 | `02_content_based.ipynb` | 3.3 | similar_movies.json, content_based_stats.csv | ~10-15 phút |
| 3 | `03_als_eval_artifacts.ipynb` | 3.4 + 3.5 | als_topn.json, metrics.csv, als_grid_search.csv | ~45-90 phút (grid 6 config × ALS) |

- Notebook 01 chạy **trước tiên** (nó unzip curated + tạo cutoffs cho split_stats.csv).
- Notebook 03 đọc `split_stats.csv` từ notebook 01 — single source of truth cho split.
- Mỗi notebook có **gate assert (KILL-*) ngay trong code**: nếu FAIL nghĩa là phải
  dừng + điều tra, KHÔNG chạy tiếp.

## Bước 4 — Copy kết quả về repo (sau khi 3 notebook PASS)

Tải các file từ Drive (hoặc chạy 1 cell trong Colab):

```python
from google.colab import files
files.download(f'{EVID}/split_stats.csv')      # và các file khác tương tự
```

Copy vào repo:
- `artifacts/` (repo): 3 file JSON serving artifacts + `model_card.json` → commit (dùng cho M2 handoff)
- `evidence/` (repo): split_stats.csv, metrics.csv, als_grid_search.csv, content_based_stats.csv
- **Ở lại Drive (không commit repo — quá lớn):** `user_history.parquet`, `models/als_v1.0.0/` —
  Person 2 lấy trực tiếp từ Drive khi import Mongo (user_history) và chạy B6 retrain gate (model)
- Cập nhật CHECKLIST_Person1.md (mục 9–13) + WORKLOG_Person1.md + MODEL_DESIGN.md

## Notes kỹ thuật (đã research trong PLAN §Research)

- **Checkpoint dir là bắt buộc** cho ALS maxIter=15 — không có nó ALS OOM chết ở iteration 20+
  (verified: stackoverflow 51979584 + Spark docs). Notebook đã set.
- **Driver memory 8g** set qua `SparkSession.builder.config` — Spark trên Colab chỉ có
  driver (local[*]), executor memory config không có tác dụng.
- **Fallback nếu OOM (plan B):** giảm grid còn rank=10 only, hoặc sample 20% users
  (`train.sampleBy('userId', fractions=...)`) — chỉ dùng khi đã thử High-RAM + checkpoint.
- Popularity `min_support` chọn 100 mặc định; justification cuối cùng lấy từ
  `metrics.csv` (so sánh Recall giữa các nguồn — INV6: giá trị chọn phải có số đo).
## Bước 5 — Person 2: consume M2 package (KHÔNG bị kẹt ở bước nào)

Sau khi 3 notebook PASS, Drive `movielens32m/` chứa đủ package. Person 2 làm như sau:

### 5.1 Import serving artifacts vào MongoDB (3 collection)
Các file JSON là **array of docs** → dùng `--jsonArray`:
```bash
mongoimport --uri "$MONGO_URI" --collection popular_movies   --file popular_movies.json --jsonArray
mongoimport --uri "$MONGO_URI" --collection similar_movies   --file similar_movies.json --jsonArray
mongoimport --uri "$MONGO_URI" --collection user_recommendations --file als_topn.json --jsonArray
```
> Lưu ý contract mapping: `als_topn.json` → collection **`user_recommendations`** (tên file ≠ tên collection, theo CONTRACTS.md §3.3).

### 5.2 Sinh `user_history` (collection thứ 4) từ user_history_seed.parquet
`user_history_seed.parquet` là RAW ratings (userId, movieId, rating, rating_ts) —
Person 2 **aggregate** thành docs theo contract §3.4 rồi insert:
```python
# mỗi doc: {userId, interaction_count, recent_movieIds, positive_movieIds, lastUpdated}
# recent_movieIds  = N phim mới nhất theo rating_ts
# positive_movieIds = phim rating >= 4.0
# streaming append (Kafka) sẽ UPDATE tiếp các doc này (interaction_count++, push recent)
```
KHÔNG insert seed parquet thẳng vào Mongo — nó chỉ là dữ liệu gốc để aggregate.

### 5.3 Load ALS model (cho demo / B6 retrain so sánh — không cần cho serving online)
```python
from pyspark.ml.recommendation import ALSModel
model = ALSModel.load('/content/drive/MyDrive/movielens32m/models/als_v1.0.0')
```
Serving online KHÔNG load model — đọc `user_recommendations` collection (precomputed Top-N).

### 5.4 Mọi metadata khác → đọc `artifacts/model_card.json`
- config ALS đã chọn + RMSE val/test + split cutoffs + đường dẫn mọi artifact
- min_support Popularity + justification → xem repo `evidence/metrics.csv` + MODEL_DESIGN.md
- Nếu thiếu gì → kiểm tra model_card trước khi hỏi Person 1 (mọi đường dẫn ghi sẵn trong đó)

### 5.5 Version rule (CONTRACTS §6)
`v1.0.0` active. Person 2 không đổi version khi import; khi Person 1 chạy B6 retrain →
candidate `v1.1.0`, promotion gate PASS mới activate atomically (fail ⟹ v1.0.0 keeps serving).
