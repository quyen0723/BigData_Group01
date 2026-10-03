## ADDED Requirements

### Requirement: Admin shell with sidebar sections
The React admin page SHALL have a sidebar with the sections Tổng quan, Case test, Người dùng, Phim, Model and Nhật ký. Each section SHALL have its own URL hash (`#/overview`, `#/cases`, `#/users/<id>`, `#/movies`, `#/models`, `#/log`), so reloading the page or sharing the link opens the same section. The header SHALL show the active model version and a link to the user page.

#### Scenario: Reload keeps the section
- **WHEN** the admin opens `#/users/591751` and reloads the page
- **THEN** the Người dùng section opens for user 591751

#### Scenario: Unknown hash
- **WHEN** the page opens with an unknown hash
- **THEN** it shows Tổng quan

### Requirement: Existing admin features carried over
The React admin page SHALL provide everything the current admin page provides: the 12 case tests (`free`, `c1`–`c9`, `als`, `noals`) with the same expected text and an observed result; recommendations with star rating and status polling; the user's internal state (tier, interaction count, recent and positive movies, pipeline last batch and time); adding a demo movie with a title and genres; deleting a demo movie; the model versions with their gate checks; the retrain progress; and an event log of the session's actions with times.

#### Scenario: Case test content unchanged
- **WHEN** the admin selects case `c3`
- **THEN** the expected text is the same as on the old page and the observed result is computed from the live API

#### Scenario: Deleting needs confirmation
- **WHEN** the admin clicks delete on a demo movie
- **THEN** a confirmation dialog appears, and the movie is deleted only after confirming

#### Scenario: Event log
- **WHEN** the admin rates a movie and the rating is applied
- **THEN** the event log shows the sent rating and the applied status with their times
