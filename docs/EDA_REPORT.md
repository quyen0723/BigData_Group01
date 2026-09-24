# EDA_REPORT — MovieLens 32M Curated Data

_Generated: 2026-09-24T18:41:46.726277Z by `src/analytics/eda.py` (re-run to reproduce every number in this report)._

## 1. Dataset overview
| table | rows | source |
|---|---:|---|
| curated_ratings | 32,000,204 | `spark.read.parquet('data/curated/curated_ratings')` |
| curated_movies | 87,585 | `spark.read.parquet('data/curated/curated_movies')` |
| curated_tags | 2,000,072 | `spark.read.parquet('data/curated/curated_tags')` |
| distinct users | 200,948 | `ratings.select('userId').distinct().count()` |
| rating period | 1995-01-09 18:46:44 .. 2023-10-13 09:29:07 | `ratings.agg(min/max rating_ts)` |
| distinct movies rated | 84,432 |
## 2. Data quality (measured in B1.2 — see evidence/b1_2_clean.txt)
| check | result |
|---|---|
| null in key columns (ratings/movies/tags) | 0 / 0 / 0 |
| invalid rating values (not in 0.5..5.0 step 0.5) | 0 |
| duplicate (userId, movieId) in ratings | 0 |
| ratings with movieId unmatched to movies | 0 |
| movies with zero ratings | 3,153 (informational — not removed, kept in curated_movies) |
| movies with '(no genres listed)' | 7,080 |
| tags with RFC-4180 escaped quotes | 244 (parser: quote/escape='"', verified 0 null keys) |
## 3. Rating distribution
| rating | count | share |
|---:|---:|---:|
| 0.5 | 525,132 | 1.64% |
| 1.0 | 946,675 | 2.96% |
| 1.5 | 531,063 | 1.66% |
| 2.0 | 2,028,622 | 6.34% |
| 2.5 | 1,685,386 | 5.27% |
| 3.0 | 6,054,990 | 18.92% |
| 3.5 | 4,290,105 | 13.41% |
| 4.0 | 8,367,654 | 26.15% |
| 4.5 | 2,974,000 | 9.29% |
| 5.0 | 4,596,577 | 14.36% |
| **mean** | | **3.5404** |
| **std** | | **1.0590** |
| **median** | | **3.5** |
| share rating >= 4.0 (relevant-item threshold per PRD) | 49.81% |
## 4. User activity
| stat | ratings/user |
|---|---:|
| min | 20.0 |
| max | 33,332.0 |
| mean | 159.2 |
| median | 73.0 |
| p90 | 364.0 |
| p99 | 1,287.0 |
Every user has >= 20 ratings (PRD FACT): measured min = 20 → confirmed.
## 5. Movie popularity (long tail)
- movies with < 10 ratings: 52,471 (62.1% of rated movies)
- movies with < 50 ratings: 68,398 (81.0% of rated movies)
- movies with < 100 ratings: 72,241 (85.6% of rated movies)
- movies with < 500 ratings: 78,206 (92.6% of rated movies)
| rank | movieId | title | ratings | avg rating |
|---:|---:|---|---:|---:|
| 1 | 318 | Shawshank Redemption, The (1994) | 102,929 | 4.40 |
| 2 | 356 | Forrest Gump (1994) | 100,296 | 4.05 |
| 3 | 296 | Pulp Fiction (1994) | 98,409 | 4.20 |
| 4 | 2571 | Matrix, The (1999) | 93,808 | 4.16 |
| 5 | 593 | Silence of the Lambs, The (1991) | 90,330 | 4.15 |
| 6 | 260 | Star Wars: Episode IV - A New Hope (1977) | 85,010 | 4.10 |
| 7 | 2959 | Fight Club (1999) | 77,332 | 4.23 |
| 8 | 480 | Jurassic Park (1993) | 75,233 | 3.70 |
| 9 | 527 | Schindler's List (1993) | 73,849 | 4.24 |
| 10 | 4993 | Lord of the Rings: The Fellowship of the Ring, The (2001) | 73,122 | 4.09 |
## 6. Genre analysis
| genre | movies | total ratings | mean of movie avg rating |
|---|---:|---:|---:|
| Drama | 33,152 | 13,973,271 | 3.12 |
| Comedy | 22,448 | 11,206,926 | 2.99 |
| Action | 9,296 | 9,665,213 | 2.84 |
| Thriller | 11,555 | 8,679,464 | 2.84 |
| Adventure | 5,156 | 7,590,522 | 2.94 |
| Sci-Fi | 4,797 | 5,717,337 | 2.70 |
| Romance | 10,048 | 5,524,615 | 3.09 |
| Crime | 6,704 | 5,373,051 | 3.02 |
| Fantasy | 3,784 | 3,702,759 | 2.94 |
| Children | 4,447 | 2,731,841 | 2.92 |
| Mystery | 3,894 | 2,615,322 | 2.94 |
| Horror | 8,468 | 2,492,315 | 2.55 |
| Animation | 4,586 | 2,214,562 | 3.06 |
| War | 2,225 | 1,594,110 | 3.17 |
| IMAX | 195 | 1,494,179 | 3.24 |
| Musical | 1,033 | 1,159,516 | 3.19 |
| Western | 1,489 | 596,654 | 2.91 |
| Documentary | 9,103 | 427,353 | 3.34 |
| Film-Noir | 350 | 304,710 | 3.32 |
## 7. Temporal distribution
| year | ratings | (from partition column) |
|---:|---:|
| 1995 | 4 |
| 1996 | 1,570,413 |
| 1997 | 686,173 |
| 1998 | 301,603 |
| 1999 | 1,172,746 |
| 2000 | 1,913,248 |
| 2001 | 1,159,117 |
| 2002 | 850,824 |
| 2003 | 1,011,617 |
| 2004 | 1,138,374 |
| 2005 | 1,751,973 |
| 2006 | 1,142,685 |
| 2007 | 1,022,836 |
| 2008 | 1,118,198 |
| 2009 | 890,377 |
| 2010 | 860,762 |
| 2011 | 728,957 |
| 2012 | 695,293 |
| 2013 | 563,663 |
| 2014 | 518,648 |
| 2015 | 1,742,737 |
| 2016 | 1,918,442 |
| 2017 | 1,828,098 |
| 2018 | 1,391,143 |
| 2019 | 1,385,918 |
| 2020 | 1,687,312 |
| 2021 | 1,241,062 |
| 2022 | 913,352 |
| 2023 | 794,629 |
## 8. Sparsity (critical for ALS)
- rating matrix cells (users × rated movies) = 200,948 × 84,432 = 16,966,441,536
- observed ratings = 32,000,204 → density = 0.1886% (sparse: 99.8114% empty)
- avg ratings/user = 159.2; avg ratings/movie (rated only) = 379.0
## 9. Implications for modeling (every claim cites a section above)
- Rating scale skews high: mean 3.54, 49.8% of ratings >= 4.0 (§3) → Movie Mean baseline will beat naive 3.0; relevant-item threshold 4.0 (PRD) selects a majority class — ranking metrics must be interpreted with this base rate in mind.
- Matrix density 0.1886% (§8) → ALS on explicit ratings is appropriate; rank must stay modest (grid {10, 50}) to avoid overfitting sparse data.
- Long tail: substantial share of movies with < 50 ratings (§5) → Popularity needs min-support (grid {50, 100, 500}); Content-Based similarity helps tail movies.
- User history: min 20, median 73, p90 364 ratings/user (§4) → few-history tier T (tunable) should be tested around small values (e.g. 3–20); cold start must be simulated by masking (PRD risk R6).
- Tags present for 2,000,072 rows (§1) but sparse coverage → TF-IDF tag features are OPTIONAL for Content-Based; genres multi-hot is the reliable core signal.
## 10. Reproduction
```bash
.venv/bin/python src/analytics/eda.py   # regenerates this file end-to-end
```
All numbers above are computed by single Spark actions in `src/analytics/eda.py`; no number is hand-typed. (INV1/INV5 compliance)
