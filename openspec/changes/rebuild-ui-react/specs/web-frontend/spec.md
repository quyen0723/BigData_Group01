## ADDED Requirements

### Requirement: Separate user and admin pages from one frontend project
The frontend SHALL be one Vite project under `web/` that builds two pages, the user page and the admin page, as separate bundles sharing an API client, generated API types and UI components. The user page bundle MUST NOT contain the admin page's code.

#### Scenario: Two bundles
- **WHEN** `npm run build` runs in `web/`
- **THEN** the output contains `app.html` and `admin.html`, each loading its own entry script from `/ui/assets/`

#### Scenario: User page does not ship admin code
- **WHEN** the built user page entry and its imports are inspected
- **THEN** none of the admin section modules are included

### Requirement: New pages served side by side with the old ones
The API SHALL serve the built user page at `GET /app-next` and the built admin page at `GET /admin-next`. Both SHALL answer 404 when `api.demo_enabled` is false or when no build is present. The existing routes `/app`, `/admin` and `/demo` SHALL keep their previous behaviour while `api.ui` is `legacy`.

#### Scenario: Build present and demo enabled
- **WHEN** a build exists in `WEB_DIST_DIR`, `api.demo_enabled` is true and a client requests `/app-next`
- **THEN** the API returns the built user page with HTTP 200

#### Scenario: Demo disabled
- **WHEN** `api.demo_enabled` is false
- **THEN** `/app-next`, `/admin-next`, `/legacy/app` and `/legacy/admin` answer 404

#### Scenario: No build
- **WHEN** `WEB_DIST_DIR` contains no build
- **THEN** `/app-next` and `/admin-next` answer 404 and `/app`, `/admin`, `/demo` still serve the old pages

### Requirement: Switch the default pages by configuration
The configuration SHALL provide `api.ui` with values `legacy` (the default when the key is absent, so an older configuration keeps the old pages) and `react` (the value committed in `configs/serving.yaml` once the checks passed). With `react` and a build present, `/app` SHALL serve the built user page and `/admin` and `/demo` the built admin page. With `react` and no build, they SHALL serve the old pages and the API SHALL log a warning. The old pages SHALL always be available at `/legacy/app` and `/legacy/admin` while the demo flag is on.

#### Scenario: Switched to the new pages
- **WHEN** `api.ui` is `react`, a build exists and a client requests `/app`
- **THEN** the response is the built user page, and `/legacy/app` returns the old user page

#### Scenario: Switched without a build
- **WHEN** `api.ui` is `react` and no build exists
- **THEN** `/app` returns the old user page and a warning naming the missing build is logged

#### Scenario: Rollback
- **WHEN** `api.ui` is set back to `legacy` and the API restarts
- **THEN** `/app` and `/admin` serve the old pages again

### Requirement: Built assets follow the demo flag
The API SHALL serve the build's static assets under `/ui/assets/`, and SHALL answer 404 for every `/ui/` path when `api.demo_enabled` is false.

#### Scenario: Assets hidden when the demo is off
- **WHEN** `api.demo_enabled` is false and a client requests a file under `/ui/assets/`
- **THEN** the API answers 404

### Requirement: Works offline
The built pages MUST NOT load any resource from another host: scripts, styles, fonts and icons SHALL be part of the build.

#### Scenario: No external URL in the build
- **WHEN** the built HTML, CSS and JavaScript are searched for `http://` and `https://` URLs used as `src`, `href`, `@import` or `url()`
- **THEN** none points to another host

### Requirement: Container build without a local Node installation
`docker compose up --build` SHALL produce an `api` image that already contains the built pages, using a Node build stage that is not part of the final image. The Docker build context SHALL exclude data and dependency folders through `.dockerignore`.

#### Scenario: Fresh clone
- **WHEN** someone without Node runs `docker compose -f docker/docker-compose.yml up -d --build` and enables the demo
- **THEN** `/app-next` and `/admin-next` return the built pages

#### Scenario: Context excludes large folders
- **WHEN** the image is built
- **THEN** `movielens32m/`, `*.zip`, `.venv*`, `web/node_modules` and `web/dist` are not sent in the build context

### Requirement: Bundle size budget
The user page's JavaScript SHALL be at most 250 KB after gzip and the admin page's at most 350 KB after gzip.

#### Scenario: Budget checked on build
- **WHEN** the production build finishes
- **THEN** the gzip size of each page's JavaScript is recorded and is within its budget
