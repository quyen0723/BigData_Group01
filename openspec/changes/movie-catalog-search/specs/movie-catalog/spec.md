## ADDED Requirements

### Requirement: Movie list and search endpoint
The API SHALL provide `GET /movies` that lists the movies of the catalog (including demo movies), answering 404 when `api.demo_enabled` is false, before any parameter is validated. Query parameters: `q` (0 to 100 characters), `genre` (one of the 19 MovieLens genres, case-insensitive), `sort` (`title`, `ratings`, `avg` or `wr`, default `ratings`), `order` (`asc` or `desc`, default `desc`; when `sort` is `title` and `order` is not given, `asc`), `page` (at least 1) and `size` (1 to 50, default 20). The response SHALL contain `total`, `page`, `size`, `pages`, `hasStats`, `m`, `c` and `items`, each item having `movieId`, `title`, `genres` (a list), `ratings`, `trainRatings`, `newRatings`, `avgRating`, `wr` and `isDemo`. An unknown genre, an unknown `sort` or `order`, or an out-of-range number SHALL answer 422.

#### Scenario: Search by title
- **WHEN** a client requests `/movies?q=pulp`
- **THEN** the items are movies whose title contains "pulp" in any letter case, and "Pulp Fiction (1994)" is among them

#### Scenario: Every word must match
- **WHEN** a client requests `/movies?q=godfather%20part`
- **THEN** only titles containing both "godfather" and "part" are returned

#### Scenario: Filter by genre
- **WHEN** a client requests `/movies?genre=western`
- **THEN** every item has "Western" in `genres` and `total` is the number of Western movies in the catalog

#### Scenario: Demo off
- **WHEN** `api.demo_enabled` is false
- **THEN** `/movies?size=0` answers 404 (the gate runs before validation) and `POST /movies` keeps its own behaviour

#### Scenario: Invalid parameters
- **WHEN** a client requests `/movies?size=51`, `?page=0`, `?sort=popularity` or `?genre=Nonsense`
- **THEN** the API answers 422

### Requirement: Rating statistics on every row
`ratings` SHALL be the movie's stored `support` plus the ratings counted from the ledger since the baseline (a demo movie starts at 0). `trainRatings`, `newRatings`, `avgRating` and `wr` SHALL come from the same baseline-plus-ledger statistics as the popular list, with the configured `m` and the baseline's `C`; they SHALL be `null` for a movie that has no rating in the baseline or the ledger. When there is no baseline, `hasStats` SHALL be false, `avgRating` and `wr` SHALL be `null` for every row, and searching, filtering and sorting by `title` or `ratings` SHALL still work.

#### Scenario: A movie with statistics
- **WHEN** the list contains Shawshank Redemption
- **THEN** its `trainRatings` is 73,945, `avgRating` is about 4.428 and `wr` is about 4.416, and `newRatings` counts the ledger ratings for it

#### Scenario: A movie newer than the training split
- **WHEN** a movie has a `support` but no rating before the cutoff and none in the ledger
- **THEN** its `ratings` is its support, and `trainRatings`, `avgRating` and `wr` are null

#### Scenario: No baseline
- **WHEN** `movie_stats` is missing
- **THEN** the endpoint answers 200 with `hasStats` false and null averages, and `sort=avg` or `sort=wr` answers 422 with a reason that says statistics are not available

### Requirement: Sorting and pagination
Items SHALL be ordered by the requested key and then by `movieId` ascending, so the order is the same for the same data. A movie without a value for the sort key (`avg`, `wr`) SHALL come last in both directions. `pages` SHALL be `ceil(total / size)` (0 when `total` is 0), and a page beyond the last SHALL return no items with the correct `total`.

#### Scenario: Most rated first
- **WHEN** a client requests `/movies?sort=ratings&order=desc&size=5`
- **THEN** the five items have non-increasing `ratings`

#### Scenario: Missing values last
- **WHEN** a client requests `/movies?sort=avg&order=asc` and some movies have no average
- **THEN** those movies appear after every movie that has one

#### Scenario: Page beyond the end
- **WHEN** a client requests a `page` larger than `pages`
- **THEN** `items` is empty and `total` and `pages` are unchanged

### Requirement: Demo movies in the catalog
Demo movies (movieId from `new_items.id_range_start`) SHALL be listed with `isDemo` true. After a demo movie is created or deleted through the API, the next list or search SHALL reflect it without waiting for the cache time.

#### Scenario: A new demo movie is searchable at once
- **WHEN** a client creates a movie titled "Phim thử" and then requests `/movies?q=phim%20th%E1%BB%AD`
- **THEN** the movie is in the result with `isDemo` true

### Requirement: Catalog cache
The catalog (id, title, genres, support) SHALL be read from the `movies` collection once, kept sorted by movieId, and reused for 30 seconds without being read again for each request. After 30 seconds a request SHALL receive the previous copy at once while a background refresh reads the collection, so no search waits for the read.

#### Scenario: A search after the cache time does not wait
- **WHEN** a search arrives 31 seconds after the catalog was read
- **THEN** it is answered from the previous copy and the collection is read again in the background

#### Scenario: Many searches, one read
- **WHEN** 30 searches arrive within 10 seconds
- **THEN** the `movies` collection is read once
