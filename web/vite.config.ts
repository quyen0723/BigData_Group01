import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vitest/config'

// Two pages, two bundles (design D-1). Assets are referenced as /ui/assets/... so FastAPI can serve them
// from dist/assets under /ui/ and hide them when the demo flag is off (design D-9).
const API = 'http://127.0.0.1:8088'
const apiPaths = ['/recommendations', '/ratings', '/users', '/debug', '/movies', '/health', '/openapi.json']

/** Writes dist/.bundle-report.json: for every chunk its file, entry module, imports and the modules inside it.
 *  scripts/check-build.mjs reads it to prove the user page contains no admin module (specs/web-frontend). */
function bundleReport(): Plugin {
  return {
    name: 'bundle-report',
    generateBundle(_options, bundle) {
      const chunks = Object.values(bundle)
        .filter((c) => c.type === 'chunk')
        .map((c) => {
          const chunk = c as unknown as {
            fileName: string
            isEntry: boolean
            facadeModuleId: string | null
            imports: string[]
            dynamicImports: string[]
            moduleIds?: string[]
            modules?: Record<string, unknown>
          }
          return {
            file: chunk.fileName,
            isEntry: chunk.isEntry,
            facade: chunk.facadeModuleId,
            imports: chunk.imports,
            dynamicImports: chunk.dynamicImports,
            modules: chunk.moduleIds ?? Object.keys(chunk.modules ?? {}),
          }
        })
      this.emitFile({ type: 'asset', fileName: '.bundle-report.json', source: JSON.stringify(chunks, null, 1) })
    },
  }
}

export default defineConfig({
  base: '/ui/',
  plugins: [react(), tailwindcss(), bundleReport()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: { input: { app: 'app.html', admin: 'admin.html' } },
  },
  server: {
    port: 5173,
    // Same origin through the proxy, so the API needs no CORS.
    proxy: Object.fromEntries(apiPaths.map((p) => [p, { target: API, changeOrigin: false }])),
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
