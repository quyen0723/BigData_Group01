import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Providers } from '@/shared/providers'
import { installFakeApi } from '@/test/fakeApi'
import { App } from './App'

const movie = (rank: number, source = 'content') => ({
  movieId: 200 + rank,
  title: `Film ${rank} (200${rank})`,
  genres: 'Crime|Drama',
  rank,
  score: 0.016,
  source,
})
const system = {
  activeVersion: 'v1.0.0',
  versions: [],
  retrainProgress: { pending: 0, nMin: 50, watermark: null },
  demo: { ratingPollTimeoutSeconds: 60, newItemsEnabled: true, demoMovieIdStart: 9000000, tierThreshold: 10 },
  demoMovies: [],
}

function mountWithApi({ rated = 4, items = [1, 2, 3].map((r) => movie(r)) } = {}) {
  let list = items
  let total = rated
  const api = installFakeApi([
    ['GET /debug/system', () => ({ status: 200, body: system })],
    [/^GET \/users\/\d+\/ratings\?limit=1$/, () => ({ status: 200, body: { userId: 700008, total, items: [] } })],
    [
      /^GET \/users\/\d+\/ratings\?limit=50$/,
      () => ({
        status: 200,
        body: {
          userId: 700008,
          total,
          items: total ? [{ movieId: 296, title: 'Pulp Fiction (1994)', genres: 'Crime|Drama', rating: 4.5, inCatalog: true }] : [],
        },
      }),
    ],
    [
      /^GET \/recommendations\/\d+\?k=10$/,
      () => ({
        status: 200,
        body: { userId: 700008, tier: 'few_history', strategy: 'CONTENT+POPULARITY', modelVersion: 'v1.0.0', generatedAt: 'now', fallbackReason: null, recommendations: list },
      }),
    ],
    [
      'POST /ratings',
      (req) => {
        const body = req.body as { movieId: number; eventId: string }
        list = list.filter((m) => m.movieId !== body.movieId)      // once applied, the rated movie leaves the list
        total += 1
        return { status: 202, body: { eventId: body.eventId, status: 'accepted' } }
      },
    ],
    [/^GET \/ratings\/[^/]+$/, () => ({ status: 200, body: { eventId: 'x', status: 'applied', batchId: 7, ingestedAt: 'now' } })],
  ])
  render(
    <Providers>
      <App />
    </Providers>,
  )
  return api
}

beforeEach(() => {
  window.sessionStorage.clear()
  window.localStorage.clear()
})
afterEach(() => vi.unstubAllGlobals())

describe('user page', () => {
  it('starts at the account chooser with the three personas and no technical words', async () => {
    mountWithApi()
    expect(screen.getByRole('heading', { name: 'Chọn tài khoản để bắt đầu' })).toBeInTheDocument()
    for (const name of ['An', 'Bình', 'Chi']) expect(screen.getByText(name)).toBeInTheDocument()
    expect(screen.getByText(/không có mật khẩu/)).toBeInTheDocument()
    expect(await screen.findAllByText(/4 phim đã đánh giá · người dùng MovieLens #/)).not.toHaveLength(0)
    expect(document.body).not.toHaveTextContent(/tier|strategy|eventId|fallback/i)
  })

  it('signs in as a persona, shows the greeting, the banner, the feed and the history', async () => {
    mountWithApi()
    await userEvent.click(screen.getByRole('button', { name: /^An/ }))

    expect(await screen.findByRole('heading', { name: 'Xin chào, An' })).toBeInTheDocument()
    expect(await screen.findByText('Bạn đã đánh giá 4 phim.')).toBeInTheDocument()
    expect(await screen.findByRole('status', { name: /Vì sao bạn thấy/ })).toHaveTextContent('Chấm thêm 6 phim')
    expect(await screen.findByRole('heading', { level: 3, name: 'Giống phim bạn đã thích' })).toBeInTheDocument()
    expect(screen.getByText('Film 1')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Phim bạn đã đánh giá (4)' })).toBeInTheDocument()
    expect(screen.getByText('Pulp Fiction')).toBeInTheDocument()
    expect(document.title).toBe('MovieLens — Phim dành cho An')
  })

  it('remembers the signed-in account for this tab and signs out', async () => {
    mountWithApi()
    await userEvent.click(screen.getByRole('button', { name: /^An/ }))
    await screen.findByRole('heading', { name: 'Xin chào, An' })
    expect(JSON.parse(window.sessionStorage.getItem('mlapp.account')!)).toEqual({ name: 'An', userId: 700008 })

    await userEvent.click(screen.getByRole('button', { name: /Đăng xuất/ }))
    expect(await screen.findByRole('heading', { name: 'Chọn tài khoản để bắt đầu' })).toBeInTheDocument()
    expect(window.sessionStorage.getItem('mlapp.account')).toBeNull()
  })

  it('rates a movie: pending state, saved toast, applied toast, then the feed no longer has it', async () => {
    const api = mountWithApi()
    await userEvent.click(screen.getByRole('button', { name: /^An/ }))
    const card = (await screen.findByText('Film 2')).closest('article')!

    await userEvent.click(within(card).getByRole('radio', { name: 'Chấm 4 sao' }))

    expect(await screen.findByText('Đã lưu đánh giá 4 sao cho “Film 2”')).toBeInTheDocument()
    expect(await screen.findByText('Gợi ý của bạn đã được cập nhật')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('Film 2')).not.toBeInTheDocument())

    const post = api.callsTo('POST /ratings')[0]!.body as Record<string, unknown>
    expect(post).toMatchObject({ userId: 700008, movieId: 202, rating: 4 })
    expect(typeof post.eventId).toBe('string')
    expect(await screen.findByRole('heading', { name: 'Phim bạn đã đánh giá (5)' })).toBeInTheDocument()
  })

  it('shows an error toast and unlocks the stars when the rating is refused', async () => {
    installFakeApi([
      ['GET /debug/system', () => ({ status: 200, body: system })],
      [/^GET \/users\/\d+\/ratings/, () => ({ status: 200, body: { userId: 700008, total: 0, items: [] } })],
      [/^GET \/recommendations\//, () => ({ status: 200, body: { userId: 700008, tier: '0_history', strategy: 'POPULARITY', modelVersion: 'v1.0.0', generatedAt: 'now', fallbackReason: null, recommendations: [movie(1, 'popularity')] } })],
      ['POST /ratings', () => ({ status: 503, body: { detail: 'kafka delivery timed out; the rating may still be delivered, retry with the same eventId' } })],
    ])
    render(
      <Providers>
        <App />
      </Providers>,
    )
    await userEvent.click(screen.getByRole('button', { name: /^An/ }))
    expect(await screen.findByText('Bạn chưa đánh giá phim nào.')).toBeInTheDocument()
    expect(screen.getByText(/Hãy đánh giá vài phim bạn đã xem/)).toBeInTheDocument()

    const card = (await screen.findByText('Film 1')).closest('article')!
    await userEvent.click(within(card).getByRole('radio', { name: 'Chấm 3 sao' }))

    expect(await screen.findByText('Chưa lưu được đánh giá. Vui lòng thử lại.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Thử lại' })).toBeInTheDocument()
    for (const r of within(card).getAllByRole('radio')) expect(r).not.toHaveAttribute('aria-disabled')
    expect(document.body).not.toHaveTextContent(/503|kafka/i)
  })

  it('creates an account: validates the name, picks a free user id and signs in', async () => {
    const api = mountWithApi({ rated: 0 })
    await userEvent.type(screen.getByLabelText('Tên hiển thị'), '   ')
    await userEvent.click(screen.getByRole('button', { name: 'Tạo tài khoản' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Vui lòng nhập tên từ 1 đến 40 ký tự.')
    expect(api.callsTo(/^GET \/users\/5\d{5}\/ratings\?limit=1$/)).toHaveLength(0)

    await userEvent.clear(screen.getByLabelText('Tên hiển thị'))
    await userEvent.type(screen.getByLabelText('Tên hiển thị'), 'Minh')
    await userEvent.click(screen.getByRole('button', { name: 'Tạo tài khoản' }))

    expect(await screen.findByRole('heading', { name: 'Xin chào, Minh' })).toBeInTheDocument()
    const saved = JSON.parse(window.localStorage.getItem('mlapp.accounts')!) as Array<{ name: string; userId: number }>
    expect(saved).toHaveLength(1)
    expect(saved[0]!.userId).toBeGreaterThanOrEqual(500000)
    expect(saved[0]!.userId).toBeLessThan(600000)
  })

  it('leaves focus alone when a saved session is restored, and focuses the greeting after signing in', async () => {
    window.sessionStorage.setItem('mlapp.account', JSON.stringify({ name: 'An', userId: 700008 }))
    mountWithApi()
    const restored = await screen.findByRole('heading', { name: 'Xin chào, An' })
    expect(restored).not.toHaveFocus()                    // focus stays at the start of the page, before the skip link

    await userEvent.click(screen.getByRole('button', { name: /Đăng xuất/ }))
    await userEvent.click(await screen.findByRole('button', { name: /^An/ }))
    const chosen = await screen.findByRole('heading', { name: 'Xin chào, An' })
    await waitFor(() => expect(chosen).toHaveFocus())     // chosen on this page: announced to a screen reader
  })

  it('still works when browser storage throws', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    mountWithApi()
    await userEvent.click(screen.getByRole('button', { name: /^An/ }))
    expect(await screen.findByRole('heading', { name: 'Xin chào, An' })).toBeInTheDocument()
    vi.restoreAllMocks()
  })
})
