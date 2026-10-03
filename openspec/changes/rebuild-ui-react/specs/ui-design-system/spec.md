## ADDED Requirements

### Requirement: Shared design tokens with measured contrast
Both pages SHALL use one set of design tokens: background `#F8FAFC`, surface `#FFFFFF`, border `#E2E8F0`, text `#0F172A`, muted text `#475569`, primary `#2563EB` with hover `#1E40AF` and white text, accent `#FBBF24` with dark text, warning text `#B45309`. Components SHALL refer to tokens, not to raw colour values. Every text and background pair used SHALL reach at least 4.5:1, and icons and other meaningful graphics at least 3:1 against their background.

#### Scenario: Contrast check
- **WHEN** the contrast script runs over every token pair and every genre tile colour pair in use
- **THEN** every text pair is at least 4.5:1 and every icon pair at least 3:1

#### Scenario: White text on the accent is not used
- **WHEN** the accent colour is used as a background
- **THEN** its text is the dark text colour

### Requirement: Bundled typography
The pages SHALL use Fira Sans for interface text and Fira Code for numbers, identifiers and scores, both bundled with the build. If the bundled Fira Sans does not render Vietnamese diacritics correctly, the pages SHALL use the system font stack instead.

#### Scenario: Vietnamese text renders
- **WHEN** a page shows "Phim bạn đã đánh giá" and "Dành riêng cho bạn"
- **THEN** every diacritic is drawn by the chosen font without fallback glyphs or missing marks

### Requirement: Keyboard access and visible focus
Every interactive element SHALL be reachable by keyboard in visual order and SHALL show a visible focus ring. Each page SHALL offer a "skip to main content" link. Icon-only buttons SHALL have an accessible name.

#### Scenario: Keyboard-only use
- **WHEN** a user rates a movie and switches account using only the keyboard
- **THEN** every step is reachable with Tab, arrow keys and Enter, and the focused element is always visibly marked

### Requirement: Touch targets
Interactive controls SHALL be at least 40×40 px, and at least 44×44 px when the viewport is narrower than 640 px.

#### Scenario: Stars on a phone
- **WHEN** the user page is shown at 375 px wide
- **THEN** each rating star's hit area is at least 44×44 px

### Requirement: Motion
Transitions SHALL last 150–300 ms and animate only transform and opacity. Hover states SHALL NOT shift layout. When the user prefers reduced motion, non-essential animation SHALL be turned off.

#### Scenario: Reduced motion
- **WHEN** the operating system requests reduced motion
- **THEN** skeleton pulses and card transitions do not animate

### Requirement: Feedback for asynchronous work
Loading content SHALL show skeletons that keep the final layout size. Buttons that start a request SHALL be disabled while it runs. Success and error messages SHALL appear as toasts that close by themselves after about 4 seconds. Form errors SHALL be shown next to the field and announced with `role="alert"`.

#### Scenario: Submitting a form with an error
- **WHEN** the admin submits the add-movie dialog without a title
- **THEN** an error appears next to the title field, is announced to assistive technology, and nothing is sent

### Requirement: Responsive layout
The pages SHALL work without horizontal page scrolling at 375, 768, 1024 and 1440 px. Wide tables SHALL scroll inside their own container. The admin sidebar SHALL collapse into a drawer below 1024 px.

#### Scenario: Admin on a narrow screen
- **WHEN** the admin page is shown at 768 px wide
- **THEN** the sidebar is a drawer opened by a button, and no page-level horizontal scroll appears

### Requirement: Icons and colour are not the only signal
Icons SHALL come from one SVG icon set; emoji SHALL NOT be used as icons. Status (PASS/FAIL, new, error) SHALL be conveyed by text or icon in addition to colour.

#### Scenario: Gate check status
- **WHEN** a gate check failed
- **THEN** it shows a fail icon and the word FAIL, not only a red colour
