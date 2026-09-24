# WORKLOG — Person 1 (Quyên) — MovieLens Hybrid Rec System
> Ghi nhận sau MỖI bước: đã làm gì / điều tra được / số liệu đo được / quyết định.
> Số liệu trong file này chỉ trích từ evidence files tương ứng (INV1 — không gõ tay số chưa đo).

---

## 2026-09-25 — B0.1 + B0.2 (Milestone M0, commit 4fc6426)
**Đã làm:** Repo skeleton 10 thư mục, configs (spark.yaml + model.yaml), venv (pyspark 3.5.7, Python 3.12.3, Java 21), git init; freeze `contracts/CONTRACTS.md` (4 raw schemas + 4 curated + 4 serving artifacts + routing tiers + rating event) + 4 mock sample JSON.
**Điều tra/Quyết định:** 4 quyết định research từ nguồn bình duyệt — Global Temporal Split (SIGIR'23 Sun, TOIS'23 Ji, RecSys'20 Meng), ALS grid rank{10,50}/reg{0.05,0.1,0.17}/maxIter≤15, K=10 + @20, Colab full 32M khả thi CÓ ĐIỀU KIỆN (checkpoint dir bắt buộc). Chi tiết nguồn trong PLAN_Person1.md Evidence Appendix.
**Gate:** `verify_skeleton.py` PASS 4/4; mock samples PASS 4/4.

## 2026-09-25 — Data download (commit f40d69b)
**Đã làm:** `scripts/download_data.py` — 3 lớp verify: MD5 chính thức GroupLens → zip integrity → row counts (ERR2).
**Số liệu:** MD5 `d472be332d4daa821edc399621853b57` khớp GroupLens; zip 238,950,008 bytes; row counts khớp 100% PRD: ratings **32,000,204**, movies **87,585**, tags **2,000,072**, links **87,585**.
**Ghi chú điều tra:** URL đúng là `ml-32m.zip` (ml-latest-32m.zip = 404); GroupLens publish MD5 chính thức (.zip.md5).

## 2026-09-25 — B1.1 Ingest (evidence/b1_1_ingest.txt)
**Đã làm:** `src/etl/ingest.py` — explicit StructType cho 4 bảng (cấm inference), verify row counts + distinct users qua Spark.
**Điều tra được (bug #1):** `mode=FAILFAST` của Spark 3.5.7 **báo MALFORMED sai** với 244 tags.csv có escaped quote RFC-4180 hợp lệ (vd `78842,91054,"""So long, suckers!""",1593010916`). Chẩn đoán: PERMISSIVE parse đủ 2,000,072 rows / 0 malformed ⟹ lỗi parser mode, KHÔNG phải data bẩn. Fix: PERMISSIVE + cột `_corrupt` + assert 0 (giữ đảm bảo không nuốt record hỏng).
**Số liệu:** 5/5 khớp tuyệt đối: 32,000,204 / 87,585 / 2,000,072 / 87,585 / 200,948 users; dev 0.000%.
**Gate:** PASS.

## 2026-09-25 — B1.2 Clean + transform + join (evidence/b1_2_clean.txt)
**Đã làm:** `src/etl/clean_transform.py` — null checks, invalid rating, duplicate (userId,movieId), timestamp → rating_ts + year, join movieId, genre parse, 7 nhóm check đều in số đo.
**Điều tra được:** MovieLens 32M cực sạch — 0 null / 0 invalid / 0 duplicate / 0 unmatched join (đã ĐO chứng minh, không giả định). Phát hiện informational: **3,153 movies 0 ratings**, **7,080 movies "(no genres listed)"**.
**Số liệu chính:** rating period 1995-01-09 .. 2023-10-13; 244 tags RFC-4180 quotes parse OK sau fix escape.
**Gate:** PASS (critical issues = 0).

## 2026-09-25 — B1.3 Curated Parquet (evidence/b1_3_curated.txt, commit 745899c, tag M1)
**Đã làm:** `src/etl/write_curated.py` — viết 4 bảng curated (ratings partition theo `year`), read-back verify schema + counts.
**Điều tra được (bug #2):** so sánh schema sau read-back phải dùng `simpleString()` — Parquet KHÔNG round-trip `nullable`/`containsNull` flag (Spark luôn trả nullable=true). Đây là đặc tính nền tảng, không phải dữ liệu sai.
**Số liệu:** 4/4 bảng OK — ratings 32,000,204 (29 partitions year 1995–2023), movies 87,585, tags 2,000,072, links 87,585. Disk: ~506MB ratings parquet.
**Gate:** PASS. **MILESTONE M1 ĐẠT.**

## 2026-09-25 — B1.EDA Phân tích dữ liệu (docs/EDA_REPORT.md, sinh bởi eda.py)
**Đã làm:** `src/analytics/eda.py` — sinh `EDA_REPORT.md` **100% bằng code** (10 sections theo PLAN §3, không số gõ tay, tái tạo bằng 1 lệnh).
**Số liệu điều tra chính (từ report):**
- Rating distribution: mean **3.5404**, std 1.059, median 3.5; skew cao — **49.81% ratings ≥ 4.0** (ngưỡng relevant-item của PRD chọn majority class → phải nhớ khi diễn giải Recall@K)
- User activity: min 20 (xác nhận FACT PRD), median **73**, mean 159.2, p90 364, p99 1,287, max **33,332** (power user)
- Long tail nặng: **62.1% movies rated có <10 ratings**, 81.0% <50 → Popularity cần min-support; Content-Based giúp tail
- Sparsity: matrix 200,948 × 84,432 = 16.97 tỷ cells, density **0.1886%** → ALS rank khiêm tốn (grid {10,50})
- Top movies: Shawshank (102,929 ratings, avg 4.40), Forrest Gump, Pulp Fiction
- Genres: Drama nhiều nhất (33,152 phim / 13.97M ratings); Horror avg thấp nhất 2.55; IMAX chỉ 195 phim nhưng 1.49M ratings
- Temporal: 2 đỉnh 1996 (1.57M) và 2015–2020 (1.4–1.9M/năm); 1995 chỉ 4 ratings
- Tags 2,000,072 rows nhưng coverage thưa → TF-IDF tags là OPTIONAL, genres multi-hot là core signal
**Implications cho model (đã ghi trong report §9):** mọi claim trích ngược về section số đo. **Gate KILL-EDA:** PASS.
## 2026-09-25 — B2.1 Spark SQL Analytics (evidence/b2_1_spark_sql.txt)
**Đã làm:** `src/analytics/spark_sql_analytics.py` — 5 SQL analyses (Q1 most-rated, Q2 highly-rated + min support 100, Q3 genre pattern, Q4 user activity buckets, Q5 temporal 2013+) + `explain('formatted')` đầy đủ + phần PLAN INTERPRETATION.
**Điều tra được (bug #3, #4):** pyspark `df.explain()` không có kwarg `toFile` → dùng JVM `ExplainMode.fromString('formatted')`; `LATERAL VIEW` + `JOIN` trực tiếp trong 1 query gây ParseException → wrap subquery.
**Số liệu chính:**
- Q1: Shawshank 102,929 ratings (avg 4.40); khớp EDA (cross-check nội bộ nhất quán)
- Q2 (min support 100): top avg-rating — basis cho Popularity artifact
- Q4 activity buckets: 20-49: 72,604 users / 50-199: 86,147 / 200-999: 38,576 / 1000+: 3,621 (tổng = 200,948 ✓) → dữ liệu cho chọn threshold few/enough T
- Plan facts (verify trong evidence): **14 BroadcastExchange** (movies 87,585 rows broadcast, tránh shuffle 32M ratings); Q5 **PartitionFilters year >= 2013** (partition pruning); Q4 5 Exchange nodes (AQE compounding)
- 1 sửa diễn giải cho khớp số đo: Q4 mô tả "2 shuffle" → thực đo 5 Exchange → đã sửa + regenerate evidence (trung thực theo INV5)
**Gate:** PASS (5 analyses ≥ 2, plans captured, mọi claim interpretation đã đối chiếu evidence).

## 2026-09-25 — B2.2 MapReduce cross-check (evidence/b2_2_mapreduce.txt)
**Đã làm:** `src/analytics/mapreduce_stats.py` — pipeline MapReduce chuẩn (MAP movieId→(rating,1) → COMBINE per-partition → REDUCE (sum,count)→avg) trên text export của curated ratings (risk R3: MR input là CSV/text, không đọc Parquet trực tiếp). Cross-check với Spark groupBy.
**Số liệu:** MAP output **32,000,204** records; MR movies **84,432** = Spark movies 84,432; **max |avg diff| = 0.0000000000** (tol 1e-6), max |count diff| = 0, mismatches = 0, checked 84,432 movies. Top-5 khớp Q1/EDA (Shawshank 102,929 / avg 4.4046...).
**Ghi chú:** chạy in-process Python (mapper/combiner/reducer đúng vai trò) vì máy không có Hadoop install; logic tương đương Hadoop streaming (stdin/stdout) — có thể chuyển thành mapper.py/reducer.py + `hadoop jar streaming` khi cần demo rubric.
**Gate:** PASS (bảng cross-check đầy đủ trong evidence).

## 2026-09-25 — Chuẩn bị Phase 3: 3 Colab notebooks + hướng dẫn Drive
**Đã làm:** Viết `notebooks/colab/01_split_baseline.ipynb` (B3.1 split temporal 70/15/15 + KILL-LEAKAGE assert; B3.2 MovieMean RMSE + Popularity min-support grid {50,100,500} + deterministic check + artifact theo contract §3.1), `02_content_based.ipynb` (B3.3 genres multi-hot + cosine block-matrix numpy — block 2048×87,585 float32 ≈717MB/block, top-M=20 qua argpartition, contract checks 200 phim ngẫu nhiên), `03_als_eval_artifacts.ipynb` (B3.4 ALS grid 2×3 trên val RMSE + B3.5 test RMSE vs MovieMean + Recall@K/NDCG@K K∈{10,20} relevant ≥4.0 + als_topn.json remove-already-rated + KILL-CONTRACT assert). Kèm `README_COLAB_SETUP.md` (upload Drive + thứ tự chạy + copy evidence về repo). Tạo `data/curated.zip` 439MB sẵn sàng upload.
**Điều tra được (review code trước khi bàn giao):** 3 bug tự phát hiện qua syntax-check + review: (1) f-string escape `\'` gây SyntaxError → đổi sang so sánh số học (rating_ts là epoch long, cutoff là số — KHÔNG cần quotes); (2) notebook 03 có dead code `eval_list` hỏng + markdown claim "3 nguồn" trong khi code tính 2 → đã sửa trung thực thành ALS + Popularity (Content-Based per-user ranking = optional, disclose); (3) notebook 01 thiếu cell unzip curated.zip → đã thêm (nếu thiếu curated_ratings trên Drive sẽ assert ERR ngay).
**Số liệu:** 3 notebook, 31 cells, 100% code cells pass ast.parse (trừ Colab magic `!pip`); curated.zip = 439MB (459,470,738 bytes... đo bằng ls -lh — con số chính xác lấy khi cần).
**Gate:** syntax check PASS; mọi KILL-* gate là assert trong notebook (không thể chạy tiếp nếu fail).
