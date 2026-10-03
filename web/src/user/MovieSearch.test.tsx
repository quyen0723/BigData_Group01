import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { MovieRow } from '@/shared/api/types'
import { Providers } from '@/shared/providers'
import { installFakeApi } from '@/test/fakeApi'
import { movieList, movieRow } from '../admin/fixtures'
import { App } from './App'

const system = {
  activeVersion: 'v1.0.0',
  versions: [],
  retrainProgress: { pending: 0, nMin: 50, watermark: null },
  demo: { ratingPollTimeoutSeconds: 60, newItemsEnabled: true, demoMovieIdStart: 9000000, tierThreshold: 10 },
  demoMovies: [],
}
const rec = (id: number) => ({ movieId: id, title: `Suggested ${id} (2000)`, genres: 'Crime|Drama', rank: id, score: 0.016, source: 'popularity' })

const PULP = movieRow(296, { title: 'Pulp Fiction (1994)', genres: ['Comedy', 'Crime', 'Drama', 'Thriller'] })
const PULP_1972 = movieRow(59114, { title: 'Pulp (1972)', genres: ['Comedy', 'Crime', 'Thriller'] })
const SHANE = movieRow(3001, { title: 'Shane (1953)', genres: ['Western'] })

type Options = { movies?: (p: URLSearchParams) => unknown; rated?: Array<{ movieId: number; rating: number; title: string }> }

function mount({ movies = () => movieList([PULP, PULP_1972]), rated = [] }: Options = {}) {
  window.sessionStorage.setItem('mlapp.account', JSON.stringify({ name: 'An', userId: 700008 }))
  const history = [...rated]
  const api = installFakeApi([
    ['GET /debug/system', () => ({ status: 200, body: system })],
    [
      /^GET \/users\/\d+\/ratings\?limit=\d+$/,
      () => ({ status: 200, body: { userId: 700008, total: history.length, items: history.map((h) => ({ ...h, genres: 'Drama', inCatalog: true })) } }),
    ],
    [/^GET \/recommendations\//, () => ({ status: 200, body: { userId: 700008, tier: 'few_history', strategy: 'CONTENT+POPULARITY', modelVersion: 'v1.0.0', generatedAt: 'now', fallbackReason: null, recommendations: [rec(1), rec(2), rec(3)] } })],
    [
      'POST /ratings',
      (req) => {
        const b = req.body as { movieId: number; rating: number; eventId: string }
        history.push({ movieId: b.movieId, rating: b.rating, title: `Rated ${b.movieId}` })
        return { status: 202, body: { eventId: b.eventId, status: 'accepted' } }
      },
    ],
    [/^GET \/ratings\/[^/]+$/, () => ({ status: 200, body: { eventId: 'x', status: 'applied', batchId: 7, ingestedAt: 'now' } })],
    [
      /^GET \/movies\?/,
      (req) => {
        const out = movies(new URLSearchParams(req.path.split('?')[1]))
        return 'status' in (out as object) ? (out as { status: number; body: unknown }) : { status: 200, body: out }
      },
    ],
  ])
  render(
    <Providers>
      <App />
    </Providers>,
  )
  return api
}

const searchCalls = (api: ReturnType<typeof installFakeApi>) => api.callsTo(/^GET \/movies\?/)
const field = () => screen.findByLabelText('Tên phim')

/** The card of a search result (the history list below also names rated movies, so look inside the articles). */
async function cardOf(title: string): Promise<HTMLElement> {
  return waitFor(() => {
    const card = screen.getAllByRole('article').find((a) => within(a).queryByText(title) !== null)
    expect(card).toBeTruthy()
    return card!
  })
}

beforeEach(() => {
  window.sessionStorage.clear()
  window.localStorage.clear()
})
afterEach(() => vi.unstubAllGlobals())

describe('user page movie search', () => {
  it('sits above the recommendations and asks for something to search, without calling the API', async () => {
    const api = mount()
    expect(await screen.findByRole('heading', { name: 'Tìm phim để chấm' })).toBeInTheDocument()
    const search = screen.getByRole('heading', { name: 'Tìm phim để chấm' })
    const feed = await screen.findByRole('heading', { name: 'Dành cho bạn' })
    expect(search.compareDocumentPosition(feed) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByText(/Gõ tên phim hoặc chọn một thể loại để tìm/)).toBeInTheDocument()
    expect(searchCalls(api)).toHaveLength(0)
  })

  it('does not search for a single character, and says why', async () => {
    const api = mount()
    await userEvent.type(await field(), 'p')
    expect(await screen.findByText('Nhập ít nhất 2 ký tự hoặc chọn một thể loại.')).toBeInTheDocument()
    await new Promise((r) => setTimeout(r, 500))
    expect(searchCalls(api)).toHaveLength(0)
  })

  it('finds movies after the typing pauses and shows them as cards with stars, with no technical words', async () => {
    const api = mount()
    await userEvent.type(await field(), 'pulp')
    expect(await screen.findByText('Pulp Fiction')).toBeInTheDocument() // the card splits the year off the title
    expect(screen.getByText('Pulp')).toBeInTheDocument()
    const call = new URLSearchParams(searchCalls(api)[0]!.path.split('?')[1])
    expect([call.get('q'), call.get('size'), call.get('page'), call.has('genre')]).toEqual(['pulp', '12', '1', false])
    expect(searchCalls(api)).toHaveLength(1) // one request for the whole word

    const card = screen.getByText('Pulp Fiction').closest('article')!
    expect(within(card).getAllByRole('radio')).toHaveLength(5)
    expect(card).not.toHaveTextContent(/#\d|WR|tier|strategy|eventId|điểm trung bình/i)
    expect(screen.getByText('Tìm thấy 2 phim.')).toBeInTheDocument()
  })

  it('says a one-letter title is not used when a genre is selected, instead of ignoring it silently', async () => {
    const api = mount({ movies: () => movieList([SHANE]) })
    await userEvent.selectOptions(await screen.findByLabelText('Thể loại'), 'Western')
    await userEvent.type(await field(), 's')
    expect(await screen.findByText(/Tên phim cần ít nhất 2 ký tự nên chưa được dùng để lọc/)).toBeInTheDocument()
    expect(await screen.findByText('Shane')).toBeInTheDocument()
    expect(searchCalls(api).every((c) => !new URLSearchParams(c.path.split('?')[1]).has('q'))).toBe(true)
    await userEvent.type(await field(), 'h') // two letters: the title is used and the note goes away
    await waitFor(() => expect(screen.queryByText(/chưa được dùng để lọc/)).toBeNull())
    await waitFor(() => expect(new URLSearchParams(searchCalls(api).at(-1)!.path.split('?')[1]).get('q')).toBe('sh'))
  })

  it('lists a genre on its own, without a title', async () => {
    const api = mount({ movies: () => movieList([SHANE]) })
    await userEvent.selectOptions(await screen.findByLabelText('Thể loại'), 'Western')
    expect(await screen.findByText('Shane')).toBeInTheDocument()
    const call = new URLSearchParams(searchCalls(api)[0]!.path.split('?')[1])
    expect([call.get('genre'), call.has('q')]).toEqual(['Western', false])
  })

  it('rates a result through the page rating flow: the stars lock, then it says what the user gave', async () => {
    const api = mount()
    await userEvent.type(await field(), 'pulp')
    const card = await cardOf('Pulp Fiction')
    await userEvent.click(within(card).getByRole('radio', { name: 'Chấm 5 sao' }))

    await waitFor(() => expect(api.callsTo('POST /ratings')).toHaveLength(1))
    expect(api.callsTo('POST /ratings')[0]!.body).toMatchObject({ userId: 700008, movieId: 296, rating: 5 })
    expect(await screen.findByText('Đã lưu đánh giá 5 sao cho “Pulp Fiction”')).toBeInTheDocument()
    expect(await screen.findByText('Bạn đã chấm 5 sao')).toBeInTheDocument() // from the refreshed history
  })

  it('says what the user gave a movie they rated before, and lets them rate it again', async () => {
    mount({ rated: [{ movieId: 296, rating: 4.5, title: 'Pulp Fiction (1994)' }] })
    await userEvent.type(await field(), 'pulp')
    const card = await cardOf('Pulp Fiction')
    expect(await within(card).findByText('Bạn đã chấm 4,5 sao')).toBeInTheDocument()
    for (const star of within(card).getAllByRole('radio')) expect(star).not.toHaveAttribute('aria-disabled', 'true')
    expect(within(await cardOf('Pulp')).queryByText(/Bạn đã chấm/)).toBeNull()
  })

  it('loads the next twelve with "Xem thêm"', async () => {
    const all: MovieRow[] = Array.from({ length: 30 }, (_, i) => movieRow(1000 + i, { title: `Western ${String(i + 1).padStart(2, '0')} (1950)`, genres: ['Western'] }))
    const api = mount({
      movies: (p) => {
        const page = Number(p.get('page'))
        return movieList(all.slice((page - 1) * 12, page * 12), { total: 30, page, pages: 3, size: 12 })
      },
    })
    await userEvent.type(await field(), 'western')
    expect(await screen.findByText('Western 01')).toBeInTheDocument()
    expect(screen.queryByText('Western 13')).toBeNull()
    expect(screen.getByText('Tìm thấy 30 phim, đang hiện 12.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Xem thêm (12)' }))
    expect(await screen.findByText('Western 13')).toBeInTheDocument()
    expect(screen.getByText('Western 01')).toBeInTheDocument() // the first twelve stay
    expect(new URLSearchParams(searchCalls(api).at(-1)!.path.split('?')[1]).get('page')).toBe('2')

    await userEvent.click(screen.getByRole('button', { name: 'Xem thêm (6)' }))
    expect(await screen.findByText('Western 30')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Xem thêm/ })).toBeNull()
  })

  it('says when nothing is found and clears the search on request', async () => {
    mount({ movies: () => movieList([]) })
    await userEvent.type(await field(), 'zzzz')
    expect(await screen.findByText(/Không tìm thấy phim nào/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Xoá tìm kiếm' }))
    expect(screen.getByLabelText('Tên phim')).toHaveValue('')
    expect(await screen.findByText(/Gõ tên phim hoặc chọn một thể loại/)).toBeInTheDocument()
  })

  it('shows an error with a retry', async () => {
    let fail = true
    mount({ movies: () => (fail ? { status: 500, body: { detail: 'boom' } } : movieList([PULP])) })
    await userEvent.type(await field(), 'pulp')
    expect(await screen.findByText(/Chưa tìm được phim/, undefined, { timeout: 4000 })).toBeInTheDocument()
    fail = false
    await userEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByText('Pulp Fiction')).toBeInTheDocument()
  })
})
