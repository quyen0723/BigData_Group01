## ADDED Requirements

### Requirement: Create a demo movie
When `api.demo_enabled` is true, the API SHALL expose `POST /movies` accepting a JSON body with a non-empty `title` of at most 200 characters and a non-empty list of `genres`, each one of the 19 MovieLens genres (Action, Adventure, Animation, Children, Comedy, Crime, Documentary, Drama, Fantasy, Film-Noir, Horror, IMAX, Musical, Mystery, Romance, Sci-Fi, Thriller, War, Western). The API SHALL assign the next free `movieId` in the reserved demo range starting at 9,000,000, store the movie in `movies` with its title, `|`-joined genres, `support` 0 and the creation time `addedAt`, and return HTTP 201 with the assigned `movieId`. When the flag is false, the route SHALL return HTTP 404.

#### Scenario: Valid movie created
- **WHEN** a client posts `{title: "Demo Crime Story", genres: ["Crime", "Drama"]}`
- **THEN** the API returns 201 with a `movieId` of at least 9,000,000, and `movies` contains that id with `genres` equal to `Crime|Drama`

#### Scenario: Deleted id is never reused
- **WHEN** a demo movie is created, deleted, and another demo movie is created afterwards
- **THEN** the second movie receives a `movieId` greater than the first's, so ratings given to the deleted movie cannot attach to the new one

#### Scenario: Invalid genre rejected
- **WHEN** a client posts a movie whose `genres` contains `Cooking` or `(no genres listed)`
- **THEN** the API returns 422 and `movies` is unchanged

#### Scenario: Disabled outside demo
- **WHEN** `api.demo_enabled` is false
- **THEN** `POST /movies` and `DELETE /movies/{movieId}` return HTTP 404

### Requirement: Delete a demo movie
When `api.demo_enabled` is true, the API SHALL expose `DELETE /movies/{movieId}` that removes the movie from `movies` only when `movieId` is in the reserved demo range, and SHALL return HTTP 404 for any id outside the range or not present. Ratings already given to the movie MUST NOT be deleted.

#### Scenario: MovieLens catalog is protected
- **WHEN** a client calls `DELETE /movies/296`
- **THEN** the API returns 404 and movie 296 remains in `movies`

#### Scenario: Demo movie removed
- **WHEN** a client deletes a demo movie that some users have rated
- **THEN** the movie is gone from `movies` and no longer appears in any recommendation, while its ratings remain in `user_rated`

### Requirement: New-movie candidate source
For a user whose tier is `few_history` or `enough_history`, the recommendation pipeline SHALL build a genre profile from the user's seed movies (`positive_movieIds`, or `recent_movieIds` when that list is empty) and select demo movies whose `addedAt` falls within `new_items.window_days` and that share at least one genre with the profile, excluding movies the user has already rated. The candidates SHALL be ranked by genre-overlap score, then newest first, then `movieId`. The top `new_items.slots` candidates SHALL be placed in the response starting at rank `new_items.position`, shifting the other items down so the response still contains `k` items, and each placed item SHALL carry `new` in its `source`. For tier `0_history` no demo movie SHALL be placed. When `new_items.enabled` is false, responses SHALL be identical to the behaviour before this change.

#### Scenario: Matching new movie appears
- **WHEN** a demo movie with genres `Crime|Drama` is created and a user whose seed movies are mostly Crime and Drama requests recommendations
- **THEN** the response contains that movie at rank `new_items.position` with `source` containing `new`, and still contains exactly `k` items

#### Scenario: Non-matching new movie is not shown
- **WHEN** a demo movie with genres `Western` is created and the user's seed movies contain no Western
- **THEN** the movie does not appear in that user's recommendations

#### Scenario: Fresh user keeps pure popularity
- **WHEN** a user with no history requests recommendations while demo movies exist
- **THEN** the response is the popularity list with tier `0_history`, and no demo movie is placed

#### Scenario: New user plus new movie
- **WHEN** a fresh user rates one movie that shares a genre with an existing demo movie, and the rating is applied
- **THEN** the user's next recommendations are tier `few_history` and contain that demo movie with `source` containing `new`

#### Scenario: Already rated demo movie is excluded
- **WHEN** a user has rated a demo movie
- **THEN** that movie does not appear in the user's recommendations

### Requirement: Streaming accepts movies created after the pipeline started
A rating event for a demo movie created after the Structured Streaming pipeline started SHALL pass validation and be applied by the running pipeline without a restart. Validation for movie ids that exist in neither the MovieLens catalog nor the demo range MUST remain unchanged.

#### Scenario: Rating for a newly created movie is applied
- **WHEN** a demo movie is created while the pipeline is running and a client posts a rating for it through `POST /ratings`
- **THEN** `GET /ratings/{eventId}` eventually returns `applied`, and the quarantine contains no record with that `eventId`

#### Scenario: Unknown movie still quarantined
- **WHEN** an event for a `movieId` that is not in `movies` is published to Kafka directly (bypassing the API)
- **THEN** the pipeline writes it to the quarantine with reason `unknown_movie_id`
