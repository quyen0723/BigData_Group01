import { focusManager } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PopularityItem } from '@/shared/api/types'
import { Providers } from '@/shared/providers'
import { installFakeApi } from '@/test/fakeApi'
import { popularityItem, popularityResponse } from './fixtures'
import { Popularity } from './Popularity'

// WR as the API computes it (m = 1000, C = 3.5287); the fixtures use it so the table and the formula panel can be compared exactly.
const wrOf = (v: number, r: number) => (v * r + 1000 * 3.5287) / (v + 1000)

// Three movies like the real top of the list: Shawshank far ahead, then two close neighbours.
const SHAWSHANK = popularityItem(1, 318, {
  title: 'Shawshank Redemption, The (1994)', avgRating: 4.4282, support: 73_954, baseSupport: 73_945, newRatings: 9, wr: wrOf(73_954, 4.4282),
})
const CUCKOO = popularityItem(2, 1193, { title: "One Flew Over the Cuckoo's Nest (1975)", avgRating: 4.2265, support: 33_573, baseSupport: 33_573, wr: wrOf(33_573, 4.2265) })
const SAMURAI = popularityItem(3, 2019, { title: 'Seven Samurai (1954)', avgRating: 4.2583, support: 12_776, baseSupport: 12_776, wr: wrOf(12_776, 4.2583) })

function setup(initial: PopularityItem[] = [SHAWSHANK, CUCKOO, SAMURAI], over: Parameters<typeof popularityResponse>[1] = {}) {
  const state = { items: initial, over }
  const api = installFakeApi([
    ['GET /debug/popularity?n=10', () => ({ status: 200, body: popularityResponse(state.items, state.over) })],
    [
      /^GET \/debug\/popularity\?n=10&m=(\d+(\.\d+)?)$/,
      (req) => {
        const m = Number(/m=([\d.]+)/.exec(req.path)![1])
        return { status: 200, body: popularityResponse(state.items.slice().reverse().map((i, idx) => ({ ...i, rank: idx + 1 })), { ...state.over, preview: true, m }) }
      },
    ],
  ])
  const view = render(
    <Providers>
      <Popularity />
    </Providers>,
  )
  return { api, state, ...view }
}

const rowOf = (title: RegExp | string) => screen.getByRole('button', { name: title }).closest('tr') as HTMLElement

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  focusManager.setFocused(undefined)
})

describe('Popularity table', () => {
  it('shows each movie with its average, rating count, new ratings, WR and the rank against the baseline', async () => {
    setup()
    await screen.findByRole('table')
    const row = rowOf(/Shawshank/)
    expect(within(row).getByText('#1')).toBeInTheDocument()
    expect(within(row).getByText('4.4282')).toBeInTheDocument()
    expect(within(row).getByText('73,954')).toBeInTheDocument()
    expect(within(row).getByText('+9 mới')).toBeInTheDocument()
    expect(within(row).getByText('4.4162')).toBeInTheDocument()
    expect(within(row).getByText('giữ hạng gốc #1')).toBeInTheDocument()
    expect(within(rowOf(/Seven Samurai/)).getByText('12,776')).toBeInTheDocument()
    expect(screen.getByRole('table')).toHaveAccessibleName(/Top 3 phim phổ biến xếp theo weighted rating, m = 1000/)
  })

  it('explains where the numbers come from and which list new users get', async () => {
    setup()
    await screen.findByRole('table')
    expect(screen.getByText(/22,399,368/)).toBeInTheDocument()
    expect(screen.getByText(/đến 2016-10-13/)).toBeInTheDocument()
    expect(screen.getByText(/cộng/)).toHaveTextContent(/50 rating mới đã áp dụng/)
    expect(screen.getByText(/m = 1000, C = 3\.5287, cần ít nhất 100 rating/)).toBeInTheDocument()
    expect(screen.getByText(/Cờ popularity\.live đang BẬT/)).toBeInTheDocument()
  })

  it('says so when the live switch is off: new users still get the artifact', async () => {
    setup(undefined, { liveEnabled: false })
    await screen.findByRole('table')
    expect(screen.getByText(/Cờ popularity\.live đang TẮT: user mới vẫn nhận danh sách artifact/)).toBeInTheDocument()
  })

  it('compares with the baseline: a movie that moved up shows how far and from where', async () => {
    setup([SHAWSHANK, popularityItem(2, 2019, { title: 'Seven Samurai (1954)', baseRank: 3 }), popularityItem(3, 1193, { title: 'Cuckoo', baseRank: 2 })])
    await screen.findByRole('table')
    expect(within(rowOf(/Seven Samurai/)).getByText('lên 1 so với gốc #3')).toBeInTheDocument()
    expect(within(rowOf(/Cuckoo/)).getByText('xuống 1 so với gốc #2')).toBeInTheDocument()
  })
})

describe('refreshing', () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }))

  it('refreshes every 3 seconds and marks a movie that changed rank with an arrow and words, for a while', async () => {
    const { api, state } = setup()
    await screen.findByRole('table')
    expect(api.callsTo('GET /debug/popularity?n=10')).toHaveLength(1)

    state.items = [SHAWSHANK, { ...SAMURAI, rank: 2 }, { ...CUCKOO, rank: 3 }]          // Seven Samurai overtakes the Cuckoo's Nest
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100)
    })
    await waitFor(() => expect(api.callsTo('GET /debug/popularity?n=10').length).toBeGreaterThanOrEqual(2))

    const samurai = rowOf(/Seven Samurai/)
    await waitFor(() => expect(within(samurai).getByText('lên 1')).toBeInTheDocument())
    expect(samurai).toHaveAttribute('data-moved', 'up')
    expect(within(rowOf(/Cuckoo/)).getByText('xuống 1')).toBeInTheDocument()
    expect(rowOf(/Cuckoo/)).toHaveAttribute('data-moved', 'down')
    expect(within(rowOf(/Shawshank/)).queryByText(/lên|xuống/)).toBeNull()            // unchanged rows are not marked
    expect(screen.getAllByRole('status').some((s) => /Seven Samurai \(1954\) lên 1/.test(s.textContent ?? ''))).toBe(true)   // read out to screen readers

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_500)                                        // the marker does not stay for ever
    })
    await waitFor(() => expect(rowOf(/Seven Samurai/)).not.toHaveAttribute('data-moved'))
    expect(within(rowOf(/Seven Samurai/)).queryByText('lên 1')).toBeNull()
  })

  it('sends no request once the section is closed', async () => {
    const { api, unmount } = setup()
    await screen.findByRole('table')
    const before = api.callsTo(/^GET \/debug\/popularity/).length
    unmount()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(12_000)
    })
    expect(api.callsTo(/^GET \/debug\/popularity/)).toHaveLength(before)
  })

  it('sends no request while the browser tab is hidden, and goes on when it is visible again', async () => {
    const { api } = setup()
    await screen.findByRole('table')
    focusManager.setFocused(false)
    const before = api.callsTo(/^GET \/debug\/popularity/).length
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })
    expect(api.callsTo(/^GET \/debug\/popularity/)).toHaveLength(before)

    focusManager.setFocused(true)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100)
    })
    await waitFor(() => expect(api.callsTo(/^GET \/debug\/popularity/).length).toBeGreaterThan(before))
  })
})

describe('formula panel', () => {
  it('asks for a movie first, then substitutes its numbers and matches the table', async () => {
    setup()
    await screen.findByRole('table')
    expect(screen.getByText(/Bấm tên một phim trong bảng/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Seven Samurai/ }))
    const panel = screen.getByRole('region', { name: 'Công thức từng bước' })
    expect(within(panel).getByText('Seven Samurai (1954)')).toBeInTheDocument()
    expect(within(panel).getByText(/12,776 rating \(12,776 gốc \+ 0 mới\)/)).toBeInTheDocument()
    expect(within(panel).getByText(/4\.2583 \(điểm trung bình của phim\)/)).toBeInTheDocument()
    expect(within(panel).getByText(/3\.5287 \(điểm trung bình của cả tập train\)/)).toBeInTheDocument()
    expect(within(panel).getByText(/12,776\/\(12,776\+1000\) = 92\.7%/)).toBeInTheDocument()
    expect(within(panel).getByText('Phim này được tin 93% điểm riêng của nó, 7% bị kéo về điểm trung bình chung.')).toBeInTheDocument()
    expect(within(panel).getByTestId('formula-wr')).toHaveTextContent(within(rowOf(/Seven Samurai/)).getByText(SAMURAI.wr.toFixed(4)).textContent!)
    expect(screen.getByRole('button', { name: /Seven Samurai/ })).toHaveAttribute('aria-pressed', 'true')

    await userEvent.click(screen.getByRole('button', { name: /Seven Samurai/ }))     // again: closes
    expect(screen.getByText(/Bấm tên một phim trong bảng/)).toBeInTheDocument()
  })
})

describe('preview with another m', () => {
  it('shows a preview list and a notice while m is typed, and goes back when it is cleared', async () => {
    const { api } = setup()
    await screen.findByRole('table')
    const field = screen.getByLabelText('Xem trước với m khác (không đổi hệ thống)')
    await userEvent.type(field, '0')

    await waitFor(() => expect(api.callsTo('GET /debug/popularity?n=10&m=0')).toHaveLength(1), { timeout: 3000 })
    const notice = await screen.findByText(/Đang xem trước với m = 0\. Hệ thống vẫn dùng m cấu hình, danh sách user nhận không đổi\./)
    expect(notice).toHaveAttribute('role', 'status')
    expect(within(screen.getByRole('table')).getAllByRole('row')[1]).toHaveTextContent('Seven Samurai')     // the preview order
    expect(screen.getByRole('table').querySelectorAll('[data-moved]')).toHaveLength(0)                       // two different lists are not a "move"

    await userEvent.click(screen.getByRole('button', { name: 'Đặt lại' }))
    await waitFor(() => expect(screen.queryByText(/Đang xem trước/)).not.toBeInTheDocument(), { timeout: 3000 })
    expect(within(screen.getByRole('table')).getAllByRole('row')[1]).toHaveTextContent('Shawshank')
  })

  it('refuses an invalid m without asking the API', async () => {
    const { api } = setup()
    await screen.findByRole('table')
    const field = screen.getByLabelText('Xem trước với m khác (không đổi hệ thống)')
    await userEvent.type(field, '-5')
    expect(await screen.findByText('Nhập m từ 0 đến 100000.')).toBeInTheDocument()
    expect(field).toHaveAttribute('aria-invalid', 'true')
    await new Promise((r) => setTimeout(r, 600))
    expect(api.callsTo(/m=-5/)).toHaveLength(0)
    expect(api.callsTo(/m=/)).toHaveLength(0)
  })
})

describe('when the live statistics are not available', () => {
  it('says the list is the artifact, has no averages and no formula', async () => {
    const artifactItems = [
      popularityItem(1, 3, { title: 'Movie 3', avgRating: null, support: 12_000, baseSupport: 12_000, wr: 4.3, baseRank: null }),
    ]
    setup(artifactItems, { source: 'artifact', baseline: null, c: null, appliedEvents: 0 })
    await screen.findByRole('table')
    expect(screen.getByText(/Chưa có số liệu sống/)).toHaveAttribute('role', 'status')
    expect(within(rowOf(/Movie 3/)).getByText('—')).toBeInTheDocument()
    expect(within(rowOf(/Movie 3/)).getByText('ngoài top 200 ở bản gốc')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Movie 3/ }))
    expect(screen.getByText(/chỉ có WR \(4\.300\) và số rating \(12,000\)/)).toBeInTheDocument()
  })

  it('shows an error with a retry button when the call fails', async () => {
    let fail = true
    installFakeApi([['GET /debug/popularity?n=10', () => (fail ? { status: 500, body: { detail: 'boom' } } : { status: 200, body: popularityResponse([SHAWSHANK]) })]])
    render(
      <Providers>
        <Popularity />
      </Providers>,
    )
    const alert = await screen.findByText('Không tải được danh sách phổ biến.', undefined, { timeout: 4000 })
    expect(alert.closest('[role="alert"]')).not.toBeNull()
    fail = false
    await userEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByRole('table')).toBeInTheDocument()
  })
})
