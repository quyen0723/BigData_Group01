import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Providers } from '@/shared/providers'
import { installFakeApi } from '@/test/fakeApi'
import { eventLog } from './eventLog'
import { movieList, movieRow, systemStatus } from './fixtures'
import { MoviesSection } from './MoviesSection'

beforeEach(() => {
  window.sessionStorage.clear()
  eventLog.clear()
})
afterEach(() => vi.unstubAllGlobals())

describe('movies section', () => {
  it('has the demo movie panel on top and the catalog below it', async () => {
    installFakeApi([
      ['GET /debug/system', () => ({ status: 200, body: systemStatus({ demoMovies: [] }) })],
      [/^GET \/movies\?/, () => ({ status: 200, body: movieList([movieRow(296, { title: 'Pulp Fiction (1994)' })]) })],
    ])
    render(
      <Providers>
        <MoviesSection />
      </Providers>,
    )
    const demoPanel = await screen.findByRole('heading', { name: 'Phim mới (demo-only)' })
    const catalog = await screen.findByRole('heading', { name: 'Danh mục phim' })
    expect(demoPanel.compareDocumentPosition(catalog) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy() // the catalog comes after the panel
    expect(await screen.findByText('Pulp Fiction (1994)')).toBeInTheDocument()
  })

  it('reloads the catalog after a demo movie is added', async () => {
    const api = installFakeApi([
      ['GET /debug/system', () => ({ status: 200, body: systemStatus({ demoMovies: [] }) })],
      [/^GET \/movies\?/, () => ({ status: 200, body: movieList([movieRow(296, { title: 'Pulp Fiction (1994)' })]) })],
      ['POST /movies', () => ({ status: 201, body: { movieId: 9000002, title: 'Phim thử', genres: ['Crime'], addedAt: '2026-10-03T09:00:00' } })],
    ])
    render(
      <Providers>
        <MoviesSection />
      </Providers>,
    )
    await screen.findByText('Pulp Fiction (1994)')
    const before = api.callsTo(/^GET \/movies\?/).length

    await userEvent.click(screen.getByRole('button', { name: 'Thêm phim' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.type(within(dialog).getByLabelText('Tên phim'), 'Phim thử')
    await userEvent.click(within(dialog).getByRole('checkbox', { name: 'Crime' }))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Thêm phim' }))

    await waitFor(() => expect(api.callsTo('POST /movies')).toHaveLength(1))
    await waitFor(() => expect(api.callsTo(/^GET \/movies\?/).length).toBeGreaterThan(before)) // the table asked again, so the new movie shows up
  })
})
