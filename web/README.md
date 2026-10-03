# web/ — React frontend for the demo

Two pages served by the FastAPI `api` service, built from this folder (OpenSpec change `rebuild-ui-react`):

| Page | Entry | For | Routes (`api.ui: "react"`) |
|---|---|---|---|
| User app | `app.html` → `src/user` | the audience: pick a demo persona, see recommendations, rate movies | `/app`, `/app-next` |
| Admin console | `admin.html` → `src/admin` | engineers: case tests, demo movies, model lifecycle, event log | `/admin`, `/demo`, `/admin-next` |

The old static pages stay available at `/legacy/app` and `/legacy/admin` (always, whatever the flag says).
Everything is behind `api.demo_enabled` (committed value `false`; there is no authentication): with the flag off the pages,
`/legacy/*` and `/ui/assets/*` answer 404.

Stack: Vite 8 (two entries, base `/ui/`), React 19, TypeScript 5.9, Tailwind 4 + shadcn/ui (components are copied into
`src/shared/ui`), TanStack Query 5, sonner, lucide-react, Vitest + Testing Library. Fira Sans / Fira Code are bundled
(no request leaves the origin).

## Which page does `/app` serve? The `api.ui` flag

`configs/serving.yaml`:

```yaml
api:
  ui: "react"     # "legacy" = the static files in src/api/static, "react" = this build
```

`/app-next` and `/admin-next` always serve the build, so both versions can be compared side by side. Changing the flag
needs only an API restart (the config folder is mounted into the container):

```bash
docker compose -f docker/docker-compose.yml restart api
```

Rollback = set `ui: "legacy"` and restart. Nothing else changes: the API contract is the same for both.

## Run it

Production (what the demo uses): the `api` image builds this folder in a Node stage and copies `dist/` to `/app/web-dist`
(Node is not in the final image). The build runs `npm run build`, so it also runs the checks below and fails the image build
if one of them fails.

```bash
docker compose -f docker/docker-compose.yml up -d --build api
```

Development, with hot reload (needs the stack running, API on `127.0.0.1:8088`, `api.demo_enabled: true`):

```bash
cd web
npm ci
npm run dev        # http://localhost:5173/ui/app.html  and  /ui/admin.html (base is /ui/); API calls are proxied to :8088 (no CORS)
```

| Script | What it does |
|---|---|
| `npm run dev` | Vite dev server on :5173 with the API proxy (`vite.config.ts`) |
| `npm run build` | `tsc --noEmit`, `vite build`, then `scripts/check-build.mjs` (exit 1 on any failure) |
| `npm run build:only` | the same without the check script |
| `npm run check` | only the check script, on an existing `dist/` |
| `npm test` | Vitest (jsdom), no network: `src/test/fakeApi.ts` stands in for the API |
| `npm run gen:api` | regenerate `src/shared/api/schema.d.ts` from the running API's `/openapi.json` |

## What `npm run check` enforces

- gzip size of each page's JavaScript: user page ≤ 250 KB, admin page ≤ 350 KB;
- nothing is loaded from another host (HTML, CSS, and resource-like URLs in JS);
- the user page contains **no admin module**: the module graph of each entry comes from `dist/.bundle-report.json`
  (written by the `bundleReport` plugin in `vite.config.ts`);
- contrast: 36 token and genre-tile pairs, text ≥ 4.5:1, borders and focus ring ≥ 3:1.

## Layout

```
src/shared/   api client (never throws, status 0 = network error), query hooks, lib (movie, tier, sources, genre colours,
              retry ids, RatingFlow), ui (shadcn components, StarRating, MovieCard, GenreTile), styles (tokens, fonts)
src/user/     account chooser (personas, create account), Home (banner, movie search, feed rows, history), toasts
src/admin/    shell + sidebar (hash routes #/overview #/cases #/users/<id> #/movies #/popularity #/models #/log), cases, event log,
              movies (demo panel + searchable catalog table), popularity (live WR table)
src/test/     setup and the fake API
```

Things that are easy to break (each has a test):

- **Pending ratings live in `RatingFlow`, not in the cards.** A refetch can move a card to another row and mount it again;
  the stars must stay locked. `useRatingFlow` makes one flow per signed-in user and disposes it on logout / account change.
- **Retry ids:** the same `eventId` is kept after a 503 / network error / 5xx (the outcome is unknown, retry must be idempotent);
  all ids of that (user, movie) are dropped after a 202 or 422 (a later rating is a new one).
- **Accessibility:** stars are a `radiogroup` with a roving tabindex and `aria-disabled` (not `disabled`, so focus is not lost);
  the single blue `#2563EB` / `#1E40AF` is the only brand colour, genre tiles are measured by the check script.
- **Storage keys** `mlapp.account` (sessionStorage) and `mlapp.accounts` (localStorage) are the same as the old page's, so accounts
  created there still show. Storage that throws is tolerated everywhere.
