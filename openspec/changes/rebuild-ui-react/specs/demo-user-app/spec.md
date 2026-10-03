## ADDED Requirements

### Requirement: React user page keeps the existing behaviour
The React user page SHALL provide everything the current user page provides: the account chooser with personas An (700008), Bình (1) and Chi (127249) described by taste only; creating an account (name 1–40 characters, a fresh `userId` in 500000–599998 whose rating history is empty, at most 5 tries); the session kept per tab and created accounts kept in the browser; recommendations labelled in user language with a "Mới" badge for new movies; star rating with a toast, a "updating your recommendations" state, polling until `applied` or the configured timeout, and the same `eventId` reused when the same rating is retried; the rating history of the last 50 movies with the total; and a refresh when the tab regains focus. No technical term (tier, strategy, eventId, batch) SHALL appear on the page.

#### Scenario: Same journey as the old page
- **WHEN** a new account is created, rates one movie, and the rating is applied
- **THEN** the page shows the toast, the updating state, then new recommendations and the movie in the rating history, as the old page did

#### Scenario: Browser storage blocked
- **WHEN** reading or writing browser storage throws
- **THEN** the page still works for the current visit

### Requirement: Tier explanation banner
The user page SHALL show a banner explaining in plain words why these movies are shown: for a user with no ratings, that these are movies many people rated highly; for a user below the threshold, how many movies they have rated, that suggestions follow movies like the ones they liked, and how many more ratings unlock personal suggestions, with a progress bar; for a user at or above the threshold, that suggestions are learned from their ratings and similar viewers; and for the fallback reasons `als_artifact_missing`, `no_content_candidates` and `filled_from_popularity`, a matching plain sentence. The threshold SHALL come from the API. The banner SHALL be announced politely when it changes.

#### Scenario: Few ratings
- **WHEN** a user with 2 rated movies and threshold 10 opens the page
- **THEN** the banner says 2 movies were rated, suggestions follow similar movies, 8 more ratings unlock personal suggestions, and the progress bar shows 2 of 10

#### Scenario: No personal model yet
- **WHEN** the response has `fallbackReason = als_artifact_missing`
- **THEN** the banner says there is no personal profile yet and suggestions follow movies similar to liked ones, without technical terms

### Requirement: System status exposes the tier threshold
`GET /debug/system` SHALL include `tierThreshold` in its `demo` block, equal to `routing.T_few_enough`. Existing fields SHALL be unchanged.

#### Scenario: Threshold available
- **WHEN** a client requests `/debug/system` with the demo enabled
- **THEN** `demo.tierThreshold` equals the configured threshold and every previous field is still present

### Requirement: Recommendations grouped by source
Each recommendation SHALL be assigned the first of `new`, `als`, `content`, `popularity` found in its source label, including combined labels such as `als+content`. When at least two sources are present, the page SHALL show one row per source titled "Mới thêm", "Dành riêng cho bạn", "Giống phim bạn đã thích" and "Đang được yêu thích", ordered by the best rank in each row. When only one source is present, the page SHALL show a single grid under that source's title. Every card SHALL keep its original rank number.

#### Scenario: Two sources
- **WHEN** the response has 3 `als` and 7 `content` items
- **THEN** the page shows a "Dành riêng cho bạn" row and a "Giống phim bạn đã thích" row, each card showing its original rank

#### Scenario: One source
- **WHEN** all 10 items are `content`
- **THEN** the page shows one grid titled "Giống phim bạn đã thích"

#### Scenario: Combined label
- **WHEN** an item's source is `als+content`
- **THEN** it is placed in the "Dành riêng cho bạn" row

### Requirement: Genre tiles on movie cards
Each movie card SHALL show a tile coloured by the colour family of the movie's first genre, with that genre's icon and name, and the release year taken from a trailing "(YYYY)" in the title when present. All 19 MovieLens genres and "(no genres listed)" SHALL have a colour family and an icon.

#### Scenario: Year and genre
- **WHEN** the card shows "Pulp Fiction (1994)" with genres "Comedy|Crime|Drama|Thriller"
- **THEN** the tile uses the Comedy colour family and icon, shows "Comedy", and the card shows 1994

#### Scenario: No year in the title
- **WHEN** a demo movie title has no trailing year
- **THEN** the card shows no year and nothing else breaks

### Requirement: A pending rating survives a refresh
While a rating is waiting to be applied, the card's stars SHALL stay locked even if the recommendations are refetched or redrawn, and SHALL unlock only when the rating is applied, fails, or times out.

#### Scenario: Window focus during a pending rating
- **WHEN** a rating is pending and the tab regains focus, causing the feed to refetch
- **THEN** that movie's stars stay locked and no second rating can be sent for it
