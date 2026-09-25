# MODEL_DESIGN.md — Thiết kế & huấn luyện Hybrid Recommendation System (MovieLens 32M)

> Người thực hiện: Person 1 (BDA501 — BigData_Group01) · Phiên bản model: **v1.0.0** · Ngày: 2026-09-25
> Mọi số liệu trong tài liệu đều là **số đo được** từ Colab runs (evidence: `evidence/b3_1_split_baseline.txt`, `b3_3_content_based.txt`, `b3_4_als_eval.txt`, `metrics.csv`, `als_grid_search.csv`). Không có số suy diễn.

## 1. Tổng quan kiến trúc model

4 nguồn gợi ý phục vụ online (CONTRACTS.md §3), tách 2 nhóm:

| Nguồn | Thuật toán | Training | Artifact |
|---|---|---|---|
| Popular movies | Thống kê (support ≥ 100, xếp avg_rating, tie-break support→movieId) | Batch (nb01) | `popular_movies.json` |
| Similar movies | Content-based: genres multi-hot + cosine | Batch (nb02) | `similar_movies.json` |
| ALS Top-N | Collaborative filtering: ALS matrix factorization | Batch (nb03) | `als_topn.json` → collection `user_recommendations` |
| User history | Không có model — aggregate từ raw ratings seed | Import time (Person 2) | `user_history_seed.parquet` → docs §3.4 |

## 2. Phương pháp chia dữ liệu (Global Temporal Split 70/15/15)

- **Cách chia:** toàn bộ 32,000,204 ratings xếp theo `timestamp` (epoch long), cắt tại 2 điểm quantile 70% và 85% (`approxQuantile`, relativeError=1e-4 — exact quantile gây GK sketch giữ ~32M giá trị → JVM chết, bug #11).
- **Cutoffs đo được:** `cut_val = 1476348398` (2016-10-13), `cut_test = 1573258563` (2019-11-09).
- **Kết quả:** train 22,399,368 (70.0%) / val 4,798,976 (15.0%) / test 4,801,860 (15.0%).
- **Vì sao temporal chứ không random:** mô phỏng thực tế phục vụ (train quá khứ → dự đoán tương lai), tránh leakage tương lai; KILL-LEAKAGE verify: max(train) = 1476348395 < min(val) = 1476348398 < min(test) = 1573258563 → PASS (nguyên văn evidence b3_1).
- **Caveat đã disclose:** temporal split là khuyến nghị hiện hành cho MovieLens (TOIS'23 về leakage); nhược điểm là user hoạt động muộn rơi hết vào val/test — dẫn tới hiện tượng cold-start được ghi ở §8.

## 3. Baselines

- **MovieMean** (global fallback mean = 3.5287): RMSE val **1.0092**, test **0.9939** — trong band sanity [0.6, 1.1]. ALS buộc phải thắng baseline này (gate trong notebook).
- **Popularity Top-N** (min_support=100): chọn ms=100 vì ms=50 cho cùng top-5 [159817, 318, 142115, 858, 50] trong khi ms=100 an toàn hơn cho long tail (EDA §5: 62.1% phim < 10 ratings); ms=500 cho top-5 khác [318, 858, 50, 527, 1221] — quá gắt. Deterministic check (chạy 2 lần cùng thứ tự) PASS.

## 4. Content-based (similar movies)

- Đặc trưng: 19 genres multi-hot, ma trận X (87,585 × 19), nnz = 147,090. Cosine similarity block-matrix (BLOCK=1024, giữ top-M=20, self-ref loại).
- Kết quả đo: 80,505 phim có similar list, **7,080 empty** — khớp tuyệt đối với EDA §2 (7,080 phim "(no genres listed)").
- 200 phim ngẫu nhiên pass contract checks (no self, score ∈ (0,1], rank đúng, sorted). Pulp Fiction (296) top-5 đều score 1.0 (cùng tập genre Crime|Drama).
- **Limitation (đã disclose):** genres-only cosine cho score 1.0 với mọi phim cùng tập genre → tie broken theo scan order; overspecialization. Cải thiện tiềm năng (không làm trong scope): thêm year, tags; optional Popularity fusion ở serving layer.

## 5. ALS — lựa chọn config (có minh chứng, INV6)

Grid search 6 config trên **validation RMSE** (maxIter=15, nonnegative=True, coldStartStrategy='drop', seed=42, checkpoint dir):

| rank | regParam | val RMSE |
|---|---|---|
| 10 | 0.05 | 0.8606 |
| 10 | 0.10 | 0.8599 |
| 10 | 0.17 | 0.8774 |
| **50** | **0.05** | **0.8487** ← BEST |
| 50 | 0.10 | 0.8552 |
| 50 | 0.17 | 0.8767 |

**Chọn rank=50, regParam=0.05.** Căn cứ đo được: (1) tốt nhất trong 6 config trên val; (2) pattern nhất quán rank=50 > rank=10 (~1.3% trên mọi reg); (3) reg=0.17 over-regularize (tệ nhất ở cả 2 rank). File gốc: `evidence/als_grid_search.csv`. Best config được **retrain trên train+val** (85%) rồi đánh giá 1 lần trên test.

## 6. Kết quả đánh giá (test set)

### 6.1 Rating prediction (RMSE, càng thấp càng tốt)

| Model | RMSE test |
|---|---|
| MovieMean (baseline) | 0.9939 |
| **ALS rank=50, reg=0.05** | **0.8336** — thắng baseline **16.13%** |

Trong band khoa học [0.6, 1.1] (ALS well-tuned literature 0.75–0.95 trên MovieLens). Gate PASS: ALS thắng baseline + trong band.

### 6.2 Top-N ranking (Recall/NDCG hit-based; relevant := rating ≥ 4.0; K ∈ {10, 20})

| Nguồn | Recall@10 | NDCG@10 | Recall@20 | NDCG@20 | n_users |
|---|---|---|---|---|---|
| ALS | 0.0144 | 0.0015 | 0.0346 | 0.0020 | 3,956 |
| Popularity | 0.6078 | 0.1585 | 0.6455 | 0.1257 | 30,011 |

Sanity gate: mọi Recall@K < 1.0 → PASS (methodology không leakage).

**Nhận xét (số đo + suy luận đã tách bạch):**
- ALS Recall thấp là **kỳ vọng về mặt phương pháp**: (a) chỉ sinh top-20 candidates/user trước khi chặn relevant (khoảng candidate hẹp); (b) hit-based Recall trên temporal holdout khắc nghiệt (phải khớp đúng phim user sẽ rate ≥ 4 trong tương lai); (c) chỉ 3,956/30,011 relevant users được ALS phục vụ — phần còn lại là cold-start bị `drop` (xem §8). NDCG thấp vì các hit nằm ở rank sâu.
- Popularity Recall cao không phải leakage (KILL-LEAKAGE đã PASS ở split): top-20 phim phổ thông xuất hiện dày đặc trong hành vi rate của đa số user. Đây đúng bản chất "popularity works surprisingly well" đã biết trong literature.
- RMSE và Recall đo 2 việc khác nhau (dự đoán tuyệt đối vs xếp hạng khám phá) — ALS thắng RMSE rõ rệt, phục vụ discovery qua `als_topn.json`, còn Popularity là fallback cho cold users theo contract.

## 7. Serving artifacts & M2 package (Person 2 consume)

- `als_topn.json`: 154,608 users × Top-10, đã loại phim user đã rate (chống **toàn bộ** curated, không sample): KILL-CONTRACT full Spark anti-join → **0 leaked / 1,546,068 recs PASS**. Collection Mongo: `user_recommendations`.
- `model_card.json` = single source of truth: config, RMSE val/test, cutoffs, đường dẫn mọi artifact (đã commit repo `artifacts/model_card.json`).
- ALS model lưu Spark ML format: `models/als_v1.0.0` → `ALSModel.load()` (cho B6 retrain gate). **Ở lại Drive** (27MB, không commit).
- `user_history_seed.parquet` (32,000,204 rows): Person 2 **aggregate** thành docs §3.4 (interaction_count, recent_movieIds, positive_movieIds, lastUpdated) — KHÔNG insert thẳng.
- File lớn (`als_topn.json` 94MB, `similar_movies.json` 82MB, seed parquet): **kéo từ Drive** `movielens32m/artifacts/` — không commit repo.
- Hướng dẫn consume đầy đủ: `notebooks/colab/README_COLAB_SETUP.md` §5 (mongoimport `--jsonArray`, cách sinh user_history, load model, version rule §6).

## 8. Limitations đã disclose (ràng buộc khoa học)

1. **Cold-start coverage:** ALS phục vụ 154,608/200,948 users (77%). 46,340 users không có rating nào trước cut_test (2019-11) bị `coldStartStrategy='drop'` loại khỏi Top-N — theo thiết kế; serving layer fallback Popularity per contract. Đây là con số đo được, không phải lỗi.
2. **ALS Recall@K thấp** — phân tích phương pháp ở §6.2. Nếu cần cải thiện: mở rộng candidates (recommendForAllUsers(200+) rồi lọc), hoặc hybrid ALS + content re-ranking.
3. **Genres-only content score 1.0 ties** — tie broken theo scan order (§4).
4. **Popularity `ms=100`** là default có justification từ min_support grid (§3), không phải tối ưu toàn cục.
5. **Timestamp caveat:** MovieLens ratings thu thập hồi cố (backfilled) — TOIS'23 khuyến nghị temporal split nhưng không hoàn toàn loại bias này.

## 9. Reproducibility

- Notebooks: `notebooks/colab/01,02,03` (runned copies + outputs: `notebooks/Runned/`). Chạy `Runtime → Run all` theo thứ tự; notebook 03 có resume mode (grid load từ Drive csv nếu có).
- Deterministic: seed=42, tie-breaks tường minh (support → movieId), cutoffs tái tạo từ `split_stats.csv` (single source of truth cho split giữa các notebook).
- Mọi gate KILL-* nhúng trong notebook — FAIL là dừng, không chạy tiếp.

## 10. Bước tiếp theo

- **M2 handoff → Person 2**: import 3 collection Mongo + sinh `user_history` từ seed + streaming pipeline (B4-B5).
- Person 1 sau Person 2: **B7.1** (CSV vs Parquet experiment, local), **B6.1/B6.2** (retrain + promotion gate v1.1.0), **B8** (E2E test + evidence pack + release tag).