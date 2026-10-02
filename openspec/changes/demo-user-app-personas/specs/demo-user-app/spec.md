## ADDED Requirements

### Requirement: User app served by the API
When `api.demo_enabled` is true, the API SHALL serve a self-contained user-facing page at `GET /app` that loads no resource from the internet (no CDN script, web font or remote image). When the flag is false, `GET /app` SHALL return HTTP 404.

#### Scenario: Offline
- **WHEN** the page is opened with the Docker stack running and no internet connection
- **THEN** it renders completely and every interaction works

#### Scenario: Disabled outside demo
- **WHEN** `api.demo_enabled` is false
- **THEN** `GET /app` returns HTTP 404

### Requirement: Account chooser with demo personas
The page SHALL open on an account chooser listing three personas backed by real MovieLens users — An (userId 700008, a few crime/drama ratings), Bình (userId 1, long-time viewer of drama and romance, has an ALS document) and Chi (userId 127249, likes comedy, adventure and sci-fi, no ALS document) — plus a "create account" entry and an entry to the admin page. Personas SHALL be described only by viewing taste, never by age, gender, location or other demographics, and the chooser SHALL state that these are demo accounts without a password.

#### Scenario: Choosing a persona
- **WHEN** the visitor selects Bình
- **THEN** the page shows Bình's recommendations, which are the recommendations of userId 1

#### Scenario: Disclosure
- **WHEN** the chooser is shown
- **THEN** it states visibly that the accounts are demo accounts with no password or authentication

### Requirement: Create a demo account
The chooser SHALL let the visitor create an account by entering a display name of 1 to 40 characters in a labelled field. The page SHALL assign a userId that has no rating history (checking up to 5 random candidates), remember the account in this browser so it appears on the chooser next time, and log the visitor in.

#### Scenario: New account starts with popular movies
- **WHEN** the visitor creates the account "Minh"
- **THEN** the page greets Minh, shows popular movies, and shows an invitation to rate a few movies already watched

#### Scenario: Empty name rejected
- **WHEN** the visitor submits an empty name
- **THEN** an error is shown next to the field and no account is created

### Requirement: Session per tab
The logged-in account SHALL be kept per browser tab, so that two tabs can show two different accounts or the admin page at the same time. Logging out SHALL return the tab to the chooser.

#### Scenario: Two tabs, two roles
- **WHEN** one tab is logged in as An and another tab shows the admin page
- **THEN** reloading either tab keeps its own account or page

### Requirement: Recommendations in user language
The recommendations view SHALL show title, genres and a reason for every movie, using user language: `als` → "Dành riêng cho bạn", `new` → "Mới thêm", `content` → "Giống phim bạn đã thích", `popularity` → "Đang được yêu thích" (for combined sources, the first of als, new, content, popularity that applies). A movie from the `new` source SHALL carry a "Mới" badge. The page MUST NOT show `tier`, `strategy`, `fallbackReason`, `modelVersion`, scores, `eventId` or `batchId`.

#### Scenario: Degradation is invisible to the user
- **WHEN** the visitor is logged in as Chi, whose recommendations are produced with `fallbackReason: als_artifact_missing`
- **THEN** the page shows an ordinary list of recommendations with no error, fallback or technical wording

#### Scenario: Reasons
- **WHEN** the visitor is logged in as Bình
- **THEN** movies coming from ALS are labelled "Dành riêng cho bạn"

### Requirement: Friendly asynchronous rating feedback
Each recommendation SHALL offer a 1–5 star control. After a rating is accepted (HTTP 202) the page SHALL show a toast that dismisses itself within 5 seconds, and the rated card SHALL show a persistent "Đang cập nhật gợi ý…" state until `GET /ratings/{eventId}` returns `applied`, after which the recommendations and the rating history reload and a toast announces the update. If the rating is not applied within `api.rating_poll_timeout_seconds`, the card SHALL say that the rating is saved and recommendations will update later, without any technical diagnosis. If the API answers with an error, the page SHALL say the rating was not saved and re-enable the card.

#### Scenario: Applied
- **WHEN** the visitor rates a movie and the pipeline applies it
- **THEN** the movie disappears from the recommendations and appears first in the rating history

#### Scenario: Slow pipeline
- **WHEN** the rating is still pending after the timeout
- **THEN** the card says the rating is saved and recommendations will update later, and no message mentions streaming, pipelines or Kafka

#### Scenario: Kafka unavailable
- **WHEN** `POST /ratings` returns HTTP 503
- **THEN** the page says the rating could not be saved and asks to try again, and the stars can be used again

### Requirement: Rating history
The page SHALL show the logged-in account's most recent rated movies (at most 50) with title and stars, from `GET /users/{userId}/ratings`, and the account's total number of ratings. For an account with no ratings it SHALL show an invitation to rate movies instead of an empty list.

#### Scenario: Long-time viewer
- **WHEN** the visitor is logged in as Bình
- **THEN** the history lists recent movies with their star ratings and the total number of ratings

### Requirement: Refresh when the tab becomes visible
When the tab becomes visible again, the page SHALL reload the recommendations of the logged-in account.

#### Scenario: Admin adds a movie in another tab
- **WHEN** a demo movie matching An's taste is added on the admin tab and the presenter switches back to An's tab
- **THEN** the movie appears with the "Mới" badge without any click on An's tab

### Requirement: UI/UX baseline
The page SHALL meet these measurable criteria: text and button contrast of at least 4.5:1; star controls at least 40×40 px with an accessible name naming the value and the movie; no horizontal scrolling at a 375 px wide viewport; a visible focus indicator on every interactive element; status messages and toasts inside an `aria-live="polite"` region; no animation when `prefers-reduced-motion: reduce` is set; a placeholder (skeleton) while recommendations load; a visible label for every text input; icons drawn as inline SVG rather than emoji or text symbols.

#### Scenario: Phone width
- **WHEN** the page is shown at 375 px width
- **THEN** the document does not scroll horizontally and every star control is at least 40×40 px

#### Scenario: Keyboard
- **WHEN** a keyboard user tabs to a star control and presses Enter
- **THEN** the focus indicator is visible and the rating is submitted
