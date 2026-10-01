## ADDED Requirements

### Requirement: Admin console routes
When `api.demo_enabled` is true, the API SHALL serve the existing demo console (case-test dropdown, system panel, demo movies) at `GET /admin` and keep serving the same page at `GET /demo`. The console SHALL be titled as the admin page and SHALL link to `/app`. When the flag is false both routes SHALL return HTTP 404.

#### Scenario: Same page on both paths
- **WHEN** a client requests `GET /admin` and `GET /demo`
- **THEN** both return HTTP 200 with the same page

#### Scenario: Switching roles
- **WHEN** the presenter follows the link on the admin page
- **THEN** the user app `/app` opens

### Requirement: Admin console UI/UX fixes
The admin console SHALL fix the issues measured in the UI/UX review: below 900 px of width the side panel SHALL stack under the main column so that nothing scrolls horizontally at 375 px; star controls SHALL be at least 40×40 px with an accessible name; primary buttons SHALL reach a contrast of at least 4.5:1; every text input SHALL have a visible label; the event log SHALL be an `aria-live="polite"` region; animations SHALL be disabled under `prefers-reduced-motion: reduce`; every interactive element SHALL show a visible focus indicator.

#### Scenario: Narrow window
- **WHEN** the console is shown at 375 px width with recommendations loaded
- **THEN** the recommendations column uses the full width, the side panel follows below it, and the document does not scroll horizontally

#### Scenario: Primary button contrast
- **WHEN** the colours of the "Tải gợi ý" and "Thêm phim" buttons are measured
- **THEN** the contrast between label and background is at least 4.5:1
