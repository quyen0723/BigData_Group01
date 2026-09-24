# CONTRACTS — Frozen Data & Serving Artifact Schemas (WBS 0.2)
> **FROZEN**: any change requires BOTH members' sign-off (tracker risk R2).
> Every artifact written to MongoDB MUST match these schemas exactly (KILL-CONTRACT).
> Person 2 builds mock artifacts from this file WITHOUT asking Person 1 (gate G0).

## 1. Raw data schemas (MovieLens 32M — FACT from GroupLens README [R1])

### 1.1 ratings.csv
| field | type | constraint |
|-------|------|-----------|
| userId | int | > 0 |
| movieId | int | > 0 |
| rating | float | ∈ {0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0} |
| timestamp | long | unix epoch seconds, > 0 |

### 1.2 movies.csv
| field | type | constraint |
|-------|------|-----------|
| movieId | int | > 0, unique |
| title | string | may include year "(YYYY)" |
| genres | string | pipe-separated, ∈ {Action, Adventure, ..., Western, "(no genres listed)"} |

### 1.3 tags.csv
| field | type | constraint |
|-------|------|-----------|
| userId | int | > 0 |
| movieId | int | > 0 |
| tag | string | non-empty |
| timestamp | long | unix epoch seconds |

### 1.4 links.csv
| field | type | constraint |
|-------|------|-----------|
| movieId | int | unique |
| imdbId | int | nullable |
| tmdbId | int | nullable |

## 2. Curated Parquet (produced by WBS 1.3, consumed by analytics + modeling + streaming append)

### 2.1 curated_ratings
`userId:int, movieId:int, rating:float, timestamp:long, rating_ts:timestamp (converted)`
Partition: `year:int` (from timestamp). Unique key: (userId, movieId).

### 2.2 curated_movies
`movieId:int, title:string, genres:string, genre_list:array<string>, year:int (parsed from title, nullable)`

### 2.3 curated_tags
`userId:int, movieId:int, tag:string, timestamp:long`

### 2.4 curated_links
`movieId:int, imdbId:int, tmdbId:int`

## 3. Serving artifact contracts (produced by WBS 3.5, consumed by MongoDB + API)

All artifacts carry common metadata: `modelVersion:string (semver "vMAJOR.MINOR.PATCH")`,
`generatedAt:timestamp (ISO-8601 UTC)`.

### 3.1 popular_movies (collection: `popular_movies`)
```json
{
  "scope": "global",
  "modelVersion": "v1.0.0",
  "generatedAt": "2026-10-01T00:00:00Z",
  "items": [
    {"movieId": 296, "title": "Pulp Fiction (1994)", "genres": "Crime|Drama",
     "rank": 1, "score": 8.829, "support": 87987}
  ]
}
```
Constraints: `items` sorted by rank asc, rank starts at 1, `score >= 0`,
`support >= min_support` (value recorded in MODEL_DESIGN.md).

### 3.2 similar_movies (collection: `similar_movies`, one doc per movieId)
```json
{
  "movieId": 296,
  "modelVersion": "v1.0.0",
  "generatedAt": "2026-10-01T00:00:00Z",
  "similar": [
    {"movieId": 1084, "score": 0.917, "rank": 1}
  ]
}
```
Constraints: `similar` sorted by score desc, top **M = 20** items, score ∈ [0, 1] (cosine),
no self-reference (movieId ∉ similar.movieId).

### 3.3 als_topn (collection: `user_recommendations`, one doc per userId)
```json
{
  "userId": 1,
  "modelVersion": "v1.0.0",
  "generatedAt": "2026-10-01T00:00:00Z",
  "strategy": "ALS",
  "recommendations": [
    {"movieId": 1193, "score": 4.87, "rank": 1}
  ]
}
```
Constraints: `recommendations` sorted by rank asc, top **N = 10** items,
**no already-rated movieId** (excluded at precompute; re-checked online by Person 2).

### 3.4 user_history (collection: `user_history`, maintained by Person 2 streaming)
```json
{
  "userId": 1,
  "interaction_count": 42,
  "recent_movieIds": [1193, 296],
  "positive_movieIds": [1193],
  "lastUpdated": "2026-10-01T00:00:00Z"
}
```

## 4. History-tier routing (consumed by Person 2 router, WBS 2.4)
| tier | condition (interaction_count) | primary source | complement |
|------|-------------------------------|----------------|------------|
| 0_history | = 0 | popular_movies | none |
| few_history | 1 .. T-1 | similar_movies (via positive history) | popular_movies |
| enough_history | >= T | als_topn | similar_movies |
> T := few/enough threshold — **tunable parameter**, value chosen by experiment
> (WBS 3.x), recorded in MODEL_DESIGN.md. NOT part of this frozen contract.

## 5. Rating event (Kafka → Structured Streaming, Person 2; Person 1 validates on append)
```json
{"eventId": "uuid4", "userId": 1, "movieId": 296, "rating": 4.5, "timestamp": 1790000000, "source": "web"}
```
Constraints: eventId unique (idempotency/dedup), rating per 1.1 constraints.

## 6. Version & compatibility rules
- Breaking schema change ⟹ bump MAJOR + migrate existing Mongo docs before activation.
- modelVersion must be visible in every artifact and in API responses (PRD API contract).
- Promotion: new modelVersion activates atomically; fail ⟹ previous version keeps serving.