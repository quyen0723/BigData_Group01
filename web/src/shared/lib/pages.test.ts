import { describe, expect, it } from 'vitest'
import { siblingPage } from './pages'

describe('siblingPage', () => {
  it('stays on the new UI when the current page is a -next page', () => {
    expect(siblingPage('user', '/admin-next')).toBe('/app-next')
    expect(siblingPage('admin', '/app-next')).toBe('/admin-next')
    expect(siblingPage('user', '/admin-next/')).toBe('/app-next')
  })

  it('uses the default pages everywhere else (served by whichever UI api.ui selects)', () => {
    expect(siblingPage('user', '/admin')).toBe('/app')
    expect(siblingPage('admin', '/app')).toBe('/admin')
    expect(siblingPage('user', '/demo')).toBe('/app')
    expect(siblingPage('admin', '/ui/app.html')).toBe('/admin')
  })
})
