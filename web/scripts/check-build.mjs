// Checks of the production build (design D-12, specs/web-frontend and specs/ui-design-system):
//   1. gzip size of each page's JavaScript against its budget
//   2. no resource loaded from another host (HTML and CSS; JS only for resource-like URLs and fetch/import)
//   3. contrast of every token pair and every genre tile pair
// Run after `npm run build`:  npm run check   (exit code 1 when anything fails)
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const dist = join(root, 'dist')
const BUDGET_KB = { app: 250, admin: 350 }
let failed = false
const fail = (msg) => {
  failed = true
  console.log('  FAIL ' + msg)
}

// ---------- 1. size ----------
console.log('== JavaScript size (gzip) ==')
if (!existsSync(dist)) {
  console.log('  no dist/: run `npm run build` first')
  process.exit(1)
}
const jsOf = (page) => {
  const html = readFileSync(join(dist, `${page}.html`), 'utf8')
  const refs = [...html.matchAll(/(?:src|href)="\/ui\/(assets\/[^"]+\.js)"/g)].map((m) => m[1])
  const seen = new Set()
  const queue = [...refs]
  while (queue.length) {
    // follow the static imports between chunks
    const f = queue.pop()
    if (seen.has(f)) continue
    seen.add(f)
    const code = readFileSync(join(dist, f), 'utf8')
    // static imports (`from"./x.js"`, `import"./x.js"`) and dynamic ones (`import("./x.js")`)
    for (const m of code.matchAll(/(?:from|import)\s*\(?\s*["']\.\/([^"']+\.js)["']/g)) queue.push('assets/' + m[1])
  }
  return [...seen]
}
const pageFiles = { app: jsOf('app'), admin: jsOf('admin') }
for (const page of ['app', 'admin']) {
  const files = pageFiles[page]
  const gz = files.reduce((n, f) => n + gzipSync(readFileSync(join(dist, f))).length, 0)
  const kb = gz / 1024
  console.log(`  ${page.padEnd(6)} ${kb.toFixed(1).padStart(7)} KB gzip  (budget ${BUDGET_KB[page]} KB, ${files.length} files)`)
  if (kb > BUDGET_KB[page]) fail(`${page} page JavaScript is over its budget`)
}
const adminOnly = pageFiles.admin.filter((f) => !pageFiles.app.includes(f))
const shared = pageFiles.app.filter((f) => pageFiles.admin.includes(f))
console.log(`  files only the admin page loads: ${adminOnly.length}; shared by both pages: ${shared.length}`)
// The user page must not contain admin code. dist/.bundle-report.json (written by the bundleReport plugin in
// vite.config.ts) lists the modules inside every chunk, so this checks the real module graph of the user entry.
const reportPath = join(dist, '.bundle-report.json')
if (!existsSync(reportPath)) {
  fail('dist/.bundle-report.json is missing: cannot prove the user page has no admin code (run `npm run build`)')
} else {
  const report = JSON.parse(readFileSync(reportPath, 'utf8'))
  const byFile = new Map(report.map((c) => [c.file, c]))
  const slash = (p) => p.split(String.fromCharCode(92)).join('/')      // module ids use / on Linux, \ can appear on Windows
  const entry = (suffix) => report.find((c) => c.isEntry && typeof c.facade === 'string' && slash(c.facade).endsWith(suffix))
  const closureModules = (start) => {
    const seen = new Set()
    const modules = new Set()
    const walk = (c) => {
      if (!c || seen.has(c.file)) return
      seen.add(c.file)
      c.modules.forEach((m) => modules.add(slash(m)))
      ;[...c.imports, ...c.dynamicImports].forEach((f) => walk(byFile.get(f)))
    }
    walk(start)
    return modules
  }
  const userEntry = entry('/app.html')
  const adminEntry = entry('/admin.html')
  if (!userEntry || !adminEntry) {
    fail('could not find the user and admin entry chunks in the bundle report')
  } else {
    const userModules = closureModules(userEntry)
    const adminModules = closureModules(adminEntry)
    const leaked = [...userModules].filter((m) => m.includes('/src/admin/'))
    console.log(`  modules reachable from the user entry: ${userModules.size} (admin modules among them: ${leaked.length}); from the admin entry: ${adminModules.size}`)
    if (leaked.length) fail(`admin modules reachable from the user page: ${leaked.slice(0, 5).join(', ')}`)
    if (![...adminModules].some((m) => m.includes('/src/admin/'))) fail('the admin entry contains no src/admin module: the report cannot be trusted')
  }
}

// ---------- 2. external URLs ----------
console.log('== external resources ==')
const walk = (dir) =>
  readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(join(dir, e.name)) : [join(dir, e.name)]))
const files = walk(dist)
const extHits = []
for (const f of files) {
  const rel = f.slice(dist.length + 1).replace(/\\/g, '/')
  if (/\.(woff2?|png|jpg|svg|ico)$/.test(f)) continue
  const text = readFileSync(f, 'utf8')
  if (f.endsWith('.html')) for (const m of text.matchAll(/(?:src|href)\s*=\s*["']https?:\/\/[^"']+/g)) extHits.push(`${rel}: ${m[0]}`)
  if (f.endsWith('.css'))
    for (const m of text.matchAll(/(?:@import\s*(?:url\()?\s*["']?|url\(\s*["']?)https?:\/\/[^)"']+/g)) extHits.push(`${rel}: ${m[0]}`)
  if (f.endsWith('.js')) {
    for (const m of text.matchAll(/["'`]https?:\/\/[^"'`\s]+\.(?:js|css|woff2?|png|jpe?g|svg|json)["'`]/g)) extHits.push(`${rel}: ${m[0]}`)
    for (const m of text.matchAll(/(?:fetch|import)\(\s*["'`]https?:\/\//g)) extHits.push(`${rel}: ${m[0]}`)
  }
}
console.log(`  ${files.length} files scanned`)
if (extHits.length) extHits.forEach((h) => fail('external resource ' + h))
else console.log('  nothing is loaded from another host')
const jsHosts = new Set()
for (const f of files.filter((x) => x.endsWith('.js')))
  for (const m of readFileSync(f, 'utf8').matchAll(/https?:\/\/([a-z0-9.-]+)/gi)) jsHosts.add(m[1])
console.log(`  (hosts that only appear as text inside JS strings, never loaded: ${[...jsHosts].sort().join(', ') || 'none'})`)

// ---------- 3. contrast ----------
console.log('== contrast ==')
const lum = (hex) => {
  const c = [1, 3, 5]
    .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
}
const ratio = (a, b) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p)
  return (x + 0.05) / (y + 0.05)
}
const css = readFileSync(join(root, 'src/shared/styles/index.css'), 'utf8')
const rootBlock = css.slice(css.indexOf(':root'), css.indexOf('@theme'))
const token = {}
for (const m of rootBlock.matchAll(/--([a-z-]+):\s*(#[0-9a-f]{6})/gi)) token[m[1]] = m[2].toLowerCase()
const TEXT = 4.5
const GRAPHIC = 3
const pairs = [
  ['foreground', 'background', TEXT],
  ['foreground', 'card', TEXT],
  ['card-foreground', 'card', TEXT],
  ['muted-foreground', 'background', TEXT],
  ['muted-foreground', 'card', TEXT],
  ['muted-foreground', 'muted', TEXT],
  ['muted-foreground', 'secondary', TEXT],
  ['primary-foreground', 'primary', TEXT],
  ['primary-foreground', 'primary-hover', TEXT],
  ['primary', 'card', TEXT],
  ['primary', 'background', TEXT],
  ['primary-hover', 'card', TEXT],
  ['highlight-foreground', 'highlight', TEXT],
  ['destructive-foreground', 'destructive', TEXT],
  ['destructive', 'card', TEXT],
  ['success-foreground', 'success', TEXT],
  ['success', 'card', TEXT],
  ['warning-text', 'card', TEXT],
  ['warning-text', 'background', TEXT],
  ['accent-foreground', 'accent', TEXT],
  ['sidebar-foreground', 'sidebar', TEXT],
  ['sidebar-accent-foreground', 'sidebar-accent', TEXT],
  ['popover-foreground', 'popover', TEXT],
  ['secondary-foreground', 'secondary', TEXT],
  ['input', 'card', GRAPHIC],
  ['input', 'background', GRAPHIC],
  ['ring', 'background', GRAPHIC],
  ['ring', 'card', GRAPHIC],
]
let measured = 0
let lowest = Infinity
for (const [fg, bg, min] of pairs) {
  if (!token[fg] || !token[bg]) {
    fail(`token missing for pair ${fg} / ${bg}`)
    continue
  }
  const r = ratio(token[fg], token[bg])
  measured++
  lowest = Math.min(lowest, r)
  if (r < min) fail(`${fg} ${token[fg]} on ${bg} ${token[bg]} = ${r.toFixed(2)}:1 (needs ${min}:1)`)
}
const genres = JSON.parse(readFileSync(join(root, 'src/shared/lib/genre-colors.json'), 'utf8'))
for (const [family, c] of Object.entries(genres)) {
  if (family.startsWith('_')) continue
  const r = ratio(c.fg, c.bg)
  measured++
  lowest = Math.min(lowest, r)
  if (r < TEXT) fail(`genre tile ${family}: ${c.fg} on ${c.bg} = ${r.toFixed(2)}:1 (needs ${TEXT}:1)`)
}
console.log(`  ${measured} pairs measured, lowest ratio ${lowest.toFixed(2)}:1`)

console.log(failed ? '\nRESULT: FAIL' : '\nRESULT: PASS')
process.exit(failed ? 1 : 0)
