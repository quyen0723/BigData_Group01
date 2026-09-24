# PERSON 1 IMPLEMENTATION PLAN — MOVIELENS HYBRID REC
> Quyên (Person 1) — Data → Modeling → Evaluation → Serving Artifacts.
> Nguồn chân lý: PRD_VI, ARCH_Deep_Dive_VI, Project_Management_Tracker.xlsx (WBS).
> Ký hiệu: PRE/POST/INV/ERR/KILL, V(c) ∈ {FACT, INFERENCE, NOT_VERIFIED, REFUTED}.

## 0. Verdict
**Sẵn sàng bắt đầu T0–T2 (local)**; T3 cần quyết định môi trường Colab (dataset upload Drive / sample) trước khi chạy — xem §8 Domain Guard.

## 1. Ma trận WBS → bước plan → môi trường

| WBS | Phase | Bước plan | Môi trường | Priority | DoD rút gọn (từ tracker) |
|-----|-------|-----------|-----------|----------|--------------------------|
| 0.1 | P0 | B0.1 Repo + config + naming | Local | Critical | Cả 2 clone/run skeleton được |
| 0.2 | P0 | B0.2 Freeze data + artifact contract | Local | Critical | Person 2 dựng mock artifact không hỏi lại |
| 1.1 | P1 | B1.1 Ingest CSV explicit schema | Local (PySpark) | Critical | Schema đúng, row counts captured, no silent inference |
| 1.2 | P1 | B1.2 Clean + transform + join | Local | Critical | Quality summary, before/after counts |
| 1.3 | P1 | B1.3 Curated Parquet + read-back | Local | Critical | Read-back schema/counts consistent |
| EDA | P1 (mở rộng) | B1.EDA Phân tích dữ liệu → `EDA_REPORT.md` | Local | High (yêu cầu riêng Quyên) | Mọi số tái tạo được bằng 1 lệnh |
| 2.1 | P2 | B2.1 Spark SQL + explain('formatted') | Local | High | ≥2 phân tích + giải thích plan |
| 2.2 | P2 | B2.2 MapReduce cross-check Spark | Local (Hadoop streaming) | Medium | Reducer == Spark groupBy ± tolerance |
| 3.1 | P3 | B3.1 Data split + evaluation rules | **Colab** | Critical | Split reproducible, no leakage, relevant-item rule documented |
| 3.2 | P3 | B3.2 Movie Mean + Popularity baselines | **Colab** | High | Predictions tồn tại, Popularity Top-N deterministic |
| 3.3 | P3 | B3.3 Content-Based similar lists | **Colab** | High | movieId → similar movies hợp lệ |
| 3.4 | P3 | B3.4 ALS + precompute Top-N | **Colab** | Critical | Train reproducible, sample Top-N hợp lệ |
| 3.5 | P3 | B3.5 Evaluation + serving artifacts | **Colab** → export | Critical | Metrics full, artifacts đúng contract |
| 6.1 | P6 | B6.1 Retrain candidate | **Colab** | Critical | Candidate reproducible từ curated data mới |
| 6.2 | P6 | B6.2 Promotion gate + publish/rollback | Local/Colab | High | Fail giữ nguyên active version |
| 7.1 | P7 | B7.1 Controlled experiment + repro manifest | Local | Medium | Median 3–5 runs, người khác rerun được |
| 8.1 | P8 | B8.1 E2E integration + demo | Local + Colab | Critical | Demo reproducible từ README |
| 8.2 | P8 | B8.2 Evidence pack + freeze + tag | Local | Critical | Mọi rubric claim có evidence |

POST-3 ✓: mọi bước map 1-1 về WBS; không có bước ngoài tracker (EDA là mở rộng hợp lệ của 1.1–1.2 vì DoD của chúng yêu cầu quality evidence).

## 2. Chi tiết từng bước (in → out → KILL → Q → evidence)

### B0.1 — Repo skeleton (WBS 0.1)
- in: kiến trúc ARCH layer 1–2A + cấu trúc thư mục đã thống nhất
- out: repo + README + config (paths, versions) + folder structure
- KILL: KILL-CONTRACT (config mâu thuẫn contract B0.2)
- Q: Person 2 clone về chạy skeleton được không?
- evidence: screenshot README, tree cấu trúc, `pip freeze`
- Đề xuất cấu trúc (INFERENCE từ kiến trúc — duyệt trước khi tạo):
  ```
  configs/  data/raw/  data/curated/  src/etl/  src/analytics/
  src/modeling/  notebooks/colab/  artifacts/  evidence/  docs/
  tasks.md  PLAN_Person1.md  CHECKLIST_Person1.md
  ```

### B0.2 — Freeze contract (WBS 0.2)
- in: MovieLens schema (PRD) + 4 artifact types
- out: `docs/CONTRACTS.md` — frozen schema:
  - ratings: `userId:int, movieId:int, rating:float(0.5–5.0), timestamp:long`
  - `popular_movies`: `scope, version, [ {movieId, title, genres, rank, score, support} ]`
  - `similar_movies`: `movieId → [ {movieId_sim, score} ] (Top-M)`
  - `als_topn`: `userId → [ {movieId, score, rank} ] (Top-N)` + `modelVersion, generatedAt`
- KILL: KILL-CONTRACT — mọi artifact phải khớp 100% schema này
- Q: Person 2 dựng mock JSON từ contract không cần hỏi lại?
- evidence: CONTRACTS.md + sample JSON mỗi loại

### B1.1 — Ingest (WBS 1.1)
- in: 4 CSV MovieLens 32M
- out: `ratings_df, movies_df, tags_df, links_df` (explicit StructType)
- KILL: ERR2 — row counts lệch >10% so với số liệu tài liệu (FACT: 32,000,204 ratings / 2,000,072 tags / 87,585 movies / 200,948 users [PRD:227])
- Q: `printSchema()` khớp contract? Row counts captured?
- evidence: schema print, row counts, sample 5 rows

### B1.2 — Clean + join (WBS 1.2)
- in: 4 raw DataFrames
- out: clean DataFrames + quality summary
- checks: null per cột, rating ∉ [0.5, 5.0], duplicate (userId, movieId), timestamp → ISO, join movieId → log unmatched
- KILL: KILL-EDA (quality summary có nhận định không kèm số đo)
- Q: before/after counts + unmatched keys có ghi đầy đủ?
- evidence: `evidence/quality_summary.md` + counts

### B1.3 — Curated Parquet (WBS 1.3)
- in: clean DataFrames
- out: `data/curated/*.parquet` (partition hợp lý — đề xuất `year`) + read-back validation
- KILL: read-back lệch schema/counts ⟹ fail
- Q: đọc lại bằng PySpark cho đúng counts + schema?
- evidence: Parquet paths + read-back output (cũng là append target cho Person 2 streaming — WBS 5.2)

### B1.EDA — Phân tích dữ liệu kỹ càng (mở rộng WBS 1.1–1.2) → schema `EDA_REPORT.md`
- in: clean + curated data
- out: `docs/EDA_REPORT.md` theo schema §3 (bên dưới)
- KILL: KILL-EDA — mọi nhận định phải kèm số đo
- Q: mọi số tái tạo được bằng 1 lệnh (cell notebook / script) không?
- evidence: EDA_REPORT.md + notebook/script sinh ra nó

### B2.1 — Spark SQL (WBS 2.1)
- in: Curated Parquet
- out: ≥2 phân tích (most-rated; highly-rated + min support; genre pattern; user activity; temporal) + `explain('formatted')` + ghi chú Exchange/join/aggregate
- KILL: không giải thích được plan ⟹ section REFUTED
- Q: có ≥2 query + giải thích plan không?
- evidence: query outputs + plans (screenshots/text)

### B2.2 — MapReduce (WBS 2.2)
- in: cleaned ratings (CSV/Text — risk R3: Hadoop streaming không đọc Parquet trực tiếp)
- out: mapper/reducer (movieId → (sum, count, avg)) + comparison table vs Spark groupBy
- KILL: |MR − Spark| > tolerance ⟹ fail
- Q: comparison table khớp ± tolerance (đề xuất tolerance := max(1e-6, 0.01% tổng ratings) — ghi rõ trong output)?
- evidence: MR code + comparison table

### B3.1 — Split + evaluation rules (WBS 3.1, **Colab**)
- in: curated ratings
- out: `train/val/test` + `MODEL_DESIGN.md` §Split: seed, phương pháp split, relevant-item rule (FACT từ PRD: relevant := rating ≥ 4.0 holdout [PRD:570]), leakage checks
- KILL: KILL-LEAKAGE
- Q: rerun với seed ⟹ split counts identical?
- evidence: split counts + seed + rule document
- ⚠️ Quyết định phải chốt: **random split (MVP, disclose limitation)** hay **temporal holdout (mạnh hơn)** — PRD khuyến nghị temporal; đề xuất temporal + ghi random làm sensitivity check (INFERENCE, cần Quyên duyệt)

### B3.2 — Baselines (WBS 3.2, **Colab**)
- in: train/val/test
- out: Movie Mean (global mean fallback) + Popularity (min support) + Popularity Top-N artifact
- KILL: KILL-CONTRACT (schema artifact)
- Q: Popularity Top-N deterministic qua 2 lần chạy?
- evidence: baseline metrics + sample Top-N

### B3.3 — Content-Based (WBS 3.3, **Colab**)
- in: movies (genres) + tags
- out: Similar-Movie Lists (genres multi-hot + optional TF-IDF tags, cosine, Top-M)
- KILL: KILL-CONTRACT; similar list trống/rác ⟹ fail
- Q: lookup movieId bất kỳ trả valid similar?
- evidence: sample lookup + similarity output
- INFERENCE: Colab RAM giới hạn — nếu full 87,585×87,585 similarity quá nặng ⟹ block-matrix hoặc chỉ tính cho Top-K popular movies; quyết định ghi vào MODEL_DESIGN.md

### B3.4 — ALS (WBS 3.4, **Colab**)
- in: train ratings
- out: ALS model (`coldStartStrategy` documented) + Precomputed ALS Top-N (generate → remove rated → rank → topN)
- KILL: KILL-METRIC (RMSE bất hợp lý thấp) ∨ KILL-CONTRACT
- Q: train lại với seed ⟹ metrics identical?
- evidence: ALS config + metrics + sample Top-N
- ⚠️ ALS rank/reg/iters = tunable (INV6) — giá trị chọn phải ghi "đã thử: a, b, c; chọn X vì val metric" hoặc cite nguồn

### B3.5 — Evaluation + artifacts (WBS 3.5, **Colab**)
- in: outputs 3.2–3.4 + test
- out: `metrics.csv` (RMSE Movie Mean vs ALS; Recall@K/NDCG@K cho 3 nguồn) + 4 serving artifacts đúng contract + modelVersion/generatedAt
- KILL: KILL-LEAKAGE ∨ KILL-METRIC ∨ KILL-CONTRACT
- Q: metrics.csv đầy đủ mọi ô? Artifacts validate theo schema?
- evidence: metrics.csv + 4 artifact files → **HANDOFF cho Person 2** (M2, day 5)

### B6.1 — Retrain candidate (WBS 6.1, **Colab**)
- in: curated data sau khi Person 2 streaming append (WBS 5.2)
- out: Candidate Model Version + metrics so sánh
- KILL: candidate không reproducible ⟹ fail
- Q: job log cho thấy data mới được include?
- evidence: job log + candidate version + metrics

### B6.2 — Promotion gate (WBS 6.2)
- in: candidate metrics + active model metadata
- out: gate result (Pass → publish; Fail → keep current) + active version update
- KILL: fail path không giữ nguyên active serving ⟹ FATAL
- Q: demo fail-path: active version trước/sau identical?
- evidence: gate result + active version before/after

### B7.1 — Controlled experiment (WBS 7.1, Local)
- in: CSV vs Parquet, cùng query, fixed Spark config
- out: timing table (warm-up + 3–5 runs, median) + reproducibility manifest (versions/seeds/commands)
- KILL: thiếu 1 thành tố kiểm soát ⟹ experiment invalid
- Q: Person 2 chạy lại từ manifest được?
- evidence: timing table + manifest

### B8.1 / B8.2 — Integration & freeze (WBS 8.1, 8.2, cùng Person 2)
- out: E2E demo flow (batch → request → rating event → history update → retrain → promotion) + evidence pack + release tag
- KILL: rubric claim nào không có evidence ⟹ phải bổ sung trước khi tag
- Q: demo chạy được từ README không?

## 3. EDA plan — schema `EDA_REPORT.md`

```markdown
# EDA_REPORT — MovieLens 32M Curated Data
## 1. Dataset overview: 4 bảng, row counts, period timestamps, nguồn số (lệnh sinh từng số)
## 2. Data quality: null/dup/invalid counts trước-sau (từ B1.2)
## 3. Rating distribution: histogram buckets, mean/median/std (đo được)
## 4. User activity: ratings/user (min ≥20 — verify lại bằng số đo), distribution
## 5. Movie popularity: long-tail, % phim có < N ratings
## 6. Genre analysis: số phim/genre, ratings theo genre
## 7. Temporal: ratings theo năm
## 8. Sparsity: density user×movie (quan trọng cho ALS)
## 9. Implications cho model: mỗi nhận định ← số ở section trên
## 10. Reproduction: lệnh/cell tái tạo từng bảng số
```
- KILL-EDA áp cho mọi section; mọi số ghi kèm lệnh sinh nó (POST-5).

## 4. Model design plan — schema `MODEL_DESIGN.md` + Colab notebook plan

```markdown
# MODEL_DESIGN — MovieLens Hybrid (Person 1)
## 1. Split: phương pháp (temporal/random), seed, counts train/val/test, leakage checks
## 2. Relevant-item rule: rating ≥ 4.0 (FACT: PRD) + K cho Recall@K/NDCG@K
## 3. Movie Mean: công thức + fallback global mean
## 4. Popularity: score + min support (giá trị tunable — justification)
## 5. Content-Based: features, similarity, Top-M (M tunable — justification)
## 6. ALS: rank/reg/maxIter (tunable — đã thử gì, chọn vì sao), coldStartStrategy
## 7. Evaluation protocol: metric nào cho task nào, tolerance tái lập
## 8. Serving artifacts: 4 schema trỏ về CONTRACTS.md
## 9. Colab plan: notebook nào, upload dataset cách nào, checkpoint Drive, thời lượng ước tính
```
Notebook Colab (đề xuất): `01_split_baseline.ipynb`, `02_content_based.ipynb`, `03_als_eval_artifacts.ipynb` (INV7: mỗi notebook ghi rõ input path Drive + output artifact path).

## 5. Verify gates & double-check loop (INV3)

Sau mỗi bước n, trả lời các câu Q của bước đó bằng evidence THỰC TẾ rồi mới sang n+1:
```
Gate n: Q_n trả lời ĐÚNG? → so sánh số đo vs kỳ vọng (ERR2: lệch >10% ⟹ DỪNG)
      → update CHECKLIST_Person1.md (status + evidence link)
      → nếu Blocked: ghi blocker + owner + next action (tracker rule 5)
```
Cụ thể theo milestone: M1 (day 2, Parquet read-back), M2 (day 5, metrics + artifacts hợp lệ), M5/M6/M7/M8 chung với Person 2.

## 6. Checklist schema + trạng thái ban đầu
→ File riêng: `CHECKLIST_Person1.md` (đã tạo, status ban đầu = Not Started cho 18 mục).

## 7. Evidence Appendix

| Số liệu | Giá trị | Nguồn | V(c) |
|---------|---------|-------|------|
| Ratings | 32,000,204 | PRD §dataset / GroupLens README [R1] | FACT (verify lại bằng row count ở B1.1) |
| Tags | 2,000,072 | PRD [R1] | FACT (verify ở B1.1) |
| Movies | 87,585 | PRD [R1] | FACT (verify ở B1.1) |
| Users | 200,948 | PRD [R1] | FACT (verify ở B1.1) |
| Mọi user ≥20 ratings | — | PRD [R1] | FACT (verify ở B1.EDA §4) |
| Relevant item := rating ≥ 4.0 | — | PRD:570 | FACT |
| Few/Enough threshold | chưa chọn | tunable | NOT_VERIFIED — chọn ở B3.x sau experiment |
| α/β fusion | chưa chọn | tunable | NOT_VERIFIED — thuộc serving (Person 2), Person 1 chỉ định nghĩa chuẩn normalize |
| ALS rank/reg | chưa chọn | tunable | NOT_VERIFIED — chọn ở B3.4 với val evidence |
| K của Top-N / Recall@K | chưa chọn | tunable | NOT_VERIFIED — chốt ở B0.2 hoặc B3.1 |

## Quyết định đã research (2026-09-25, sources trong Evidence Appendix §7.1)
1. **Split = Global Temporal Split (primary)** + random split sensitivity check. Evidence: Sun SIGIR'23 (random ⟹ leakage, 59.1% bài dùng split sai); Ji TOIS'23 (split-by-timepoint ⟹ no leakage, MovieLens timestamps unreliable ⟹ phải disclose); Meng RecSys'20 (temporal = default). Ratio 70/15/15 theo cutoff thời gian (pattern LensKit ML-10M).
2. **K = 10** (khớp API `?k=10`, PRD), ranking metrics đo @10 + @20. **Top-M = 20**. **Popularity min-support grid = {50, 100, 500}** — chọn cuối bằng val result (INV6).
3. **ALS grid**: rank ∈ {10, 50}, regParam ∈ {0.05, 0.1, 0.17}, maxIter = 10–15, nonnegative=True, coldStartStrategy="drop" (eval). **KILL-METRIC band: RMSE ALS ∉ [0.6, 1.1] ⟹ điều tra** (well-tuned ALS trên MovieLens ≈ 0.7–0.9, DataCamp cite 0.633).
4. **Colab full 32M khả thi có điều kiện**: checkpoint dir bắt buộc (ALS OOM nếu thiếu), driver memory set trước JVM, rank ≤ 32, maxIter ≤ 15. Fallback nếu OOM: sample user 20% hoặc Colab Pro high-RAM. Content-Based similarity 87,585² ⟹ block-matrix / Top-K popular only.
5. **Repo structure**: giữ đề xuất §2 (B0.1).

## Evidence Appendix §7.1 — Nguồn research quyết định
| Claim | Nguồn | V(c) |
|---|---|---|
| Random split ⟹ leakage; 59.1% RecSys papers sai split | Sun, "Take a Fresh Look at Recommender Systems from an Evaluation Standpoint", SIGIR 2023, doi.org/10.1145/3539618.3591931 | FACT |
| Split-by-timepoint ⟹ no leakage; timestamps MovieLens unreliable | Ji et al., "A Critical Study on Data Leakage in RS Offline Evaluation", TOIS 2023, doi.org/10.1145/3569930 | FACT |
| Temporal global split = default field-wide | Meng et al., "Exploring Data Splitting Strategies", RecSys 2020, doi.org/10.1145/3383313.3418479 | FACT |
| ALS defaults rank=10, regParam=0.1, ALS-WR scaling | Spark docs ml-collaborative-filtering.html + PySpark ALS API | FACT |
| RMSE ALS MovieLens ≈ 0.7–0.9 (0.633 achievable) | DataCamp notes (louisazhou.gitbook.io) | FACT (verify bằng val metric của mình) |
| Colab free ~12.7GB RAM; checkpoint dir chống ALS OOM | stackoverflow.com/questions/54953967, /51979584; stackguides.com 43630917 | FACT |
| ALS 20M chạy được với driver 2g/executor 8g | github.com/recommenders-team/recommenders als_pyspark_movielens.ipynb | FACT |

## Quyết định cần Quyên duyệt trước khi bắt đầu
1. Split: temporal holdout (đề xuất, mạnh hơn) hay random (MVP)?
2. Top-N / Top-M / K: giá trị mặc định (đề xuất K=10 cho API khớp PRD; Top-M=20 similar)?
3. Colab: upload full 32M CSV lên Drive (khả thi, ~1GB) hay sample?
4. Cấu trúc repo ở B0.1 — duyệt rồi tạo.
```

**Self-check (§11):** ✓ mọi bước map về WBS; ✓ các số chưa đo đều NOT_VERIFIED; ✓ mỗi gate trả lời được ĐÚNG/SAI bằng output thực; ✓ boundary handoff M2 cho Person 2 tường minh.