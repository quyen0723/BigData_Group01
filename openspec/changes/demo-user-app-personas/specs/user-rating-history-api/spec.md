## ADDED Requirements

### Requirement: Rating history endpoint
When `api.demo_enabled` is true, the API SHALL expose `GET /users/{userId}/ratings?limit=N` returning `{userId, total, items}`, where `total` is the user's `interaction_count` and `items` lists the user's most recently rated movies in most-recent-first order, at most `limit` items (default 20, maximum 50), each with `movieId`, `title`, `genres` and `rating`. The order and the set of movies SHALL come from `user_history.recent_movieIds`, the same history the recommendation router uses. When the flag is false the route SHALL return HTTP 404.

#### Scenario: Long-time viewer
- **WHEN** a client requests `GET /users/1/ratings?limit=50`
- **THEN** the response has `total` equal to user 1's `interaction_count` and up to 50 items, each with a title and the star value stored in `user_rated`

#### Scenario: Newest first
- **WHEN** a rating for user U is applied by the pipeline
- **THEN** the next `GET /users/U/ratings` lists that movie first

#### Scenario: Unknown user
- **WHEN** a client requests the history of a user without any history
- **THEN** the API returns HTTP 200 with `total` 0 and an empty `items` list

#### Scenario: Invalid parameters
- **WHEN** `userId` is not positive or `limit` is outside 1–50
- **THEN** the API returns HTTP 422 without querying the store

#### Scenario: Disabled outside demo
- **WHEN** `api.demo_enabled` is false
- **THEN** `GET /users/{userId}/ratings` returns HTTP 404

### Requirement: Movies no longer in the catalog
A rated movie that is no longer present in `movies` (for example a deleted demo movie) SHALL still be listed, with an empty title and genres and a flag `inCatalog: false`, so the history stays truthful to what the user rated.

#### Scenario: Deleted demo movie
- **WHEN** a user rated a demo movie that was later deleted
- **THEN** the history lists that movieId with `inCatalog: false` and the star value given
