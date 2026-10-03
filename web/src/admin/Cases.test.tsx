import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Providers } from '@/shared/providers'
import { installFakeApi } from '@/test/fakeApi'
import { App } from './App'
import { eventLog } from './eventLog'
import { debugUser, recommendation, systemStatus } from './fixtures'

function setup({ seedCount = 3 }: { seedCount?: number } = {}) {
  let list = [{ id: 296, rank: 1 }, { id: 318, rank: 2 }, { id: 858, rank: 3 }]
  let count = seedCount
  const api = installFakeApi([
    ['GET /debug/system', () => ({ status: 200, body: systemStatus() })],
    ['GET /health', () => ({ status: 200, body: { status: 'ok' } })],
    [/^GET \/recommendations\/(700008|1|127249|5\d{5})(\?|$)/, (req) => ({ status: 200, body: recommendation(Number(/recommendations\/(\d+)/.exec(req.path)![1]), list) })],
    [/^GET \/debug\/users\/700008$/, () => ({ status: 200, body: debugUser(700008, count) })],
    [/^GET \/debug\/users\/5\d{5}$/, (req) => ({ status: 200, body: debugUser(Number(req.path.split('/').pop()), 0) })],
    [/^GET \/debug\/users\/1$/, () => ({ status: 200, body: debugUser(1, 146) })],
    [
      'POST /ratings',
      (req) => {
        const b = req.body as { movieId: number; eventId: string }
        list = list.filter((m) => m.id !== b.movieId)
        count += 1
        return { status: 202, body: { eventId: b.eventId, status: 'accepted' } }
      },
    ],
    [/^GET \/ratings\/[^/]+$/, () => ({ status: 200, body: { eventId: 'x', status: 'applied', batchId: 16, ingestedAt: 'now' } })],
  ])
  window.location.hash = '#/cases'
  render(
    <Providers>
      <App />
    </Providers>,
  )
  return api
}

beforeEach(() => {
  window.sessionStorage.clear()
  eventLog.clear()
})
afterEach(() => {
  vi.unstubAllGlobals()
  window.location.hash = ''
})

describe('case tests', () => {
  it('has the 12 cases in the selector', async () => {
    setup()
    const select = await screen.findByLabelText('Case test')
    expect(within(select).getAllByRole('option')).toHaveLength(12)
    expect(screen.getByRole('option', { name: '1. User có tài khoản, chưa rating' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Đủ lịch sử nhưng thiếu ALS (user 127249)' })).toBeInTheDocument()
  })

  it('case 2 loads the seeded user, shows the card, the observed line and the internal panel', async () => {
    setup()
    await userEvent.selectOptions(await screen.findByLabelText('Case test'), 'c2')

    expect(await screen.findByRole('heading', { name: 'Case 2 — User có rating mới' })).toBeInTheDocument()
    expect(await screen.findByText('Film 296')).toBeInTheDocument()
    expect(screen.getByLabelText('userId')).toHaveValue(700008)
    await waitFor(() =>
      expect(screen.getByTestId('observed')).toHaveTextContent('Quan sát: tier=few_history · strategy=CONTENT+POPULARITY · interaction_count=3 · user 700008'),
    )
    const panel = screen.getByRole('region', { name: 'Bên trong hệ thống' })
    expect(within(panel).getByText('v1.0.0')).toBeInTheDocument()
    expect(within(panel).getByText('#15 @ 2026-10-03T07:00:01')).toBeInTheDocument()
    expect(eventLog.getSnapshot().some((e) => e.text === 'case: 2. User có rating mới')).toBe(true)
  })

  it('shows rank, score and the raw source on each card (the technical view)', async () => {
    setup()
    await userEvent.selectOptions(await screen.findByLabelText('Case test'), 'c2')
    expect(await screen.findByText(/^#1 · score 0\.0160$/)).toBeInTheDocument()
    expect(screen.getAllByText(/nguồn: content/i).length).toBeGreaterThan(0)
  })

  it('a fresh-user case picks a user with no history', async () => {
    const api = setup()
    await userEvent.selectOptions(await screen.findByLabelText('Case test'), 'c1')
    await screen.findByText('Film 296')
    const id = Number((screen.getByLabelText('userId') as HTMLInputElement).value)
    expect(id).toBeGreaterThanOrEqual(500000)
    expect(id).toBeLessThan(600000)
    expect(api.callsTo(new RegExp(`^GET /debug/users/${id}$`)).length).toBeGreaterThan(0)
  })

  it('rating a movie writes the whole story to the event log and the movie leaves the list', async () => {
    setup()
    await userEvent.selectOptions(await screen.findByLabelText('Case test'), 'c2')
    const card = (await screen.findByText('Film 296')).closest('article')!
    await userEvent.click(within(card).getByRole('radio', { name: 'Chấm 4 sao' }))

    await waitFor(() => expect(screen.queryByText('Film 296')).not.toBeInTheDocument())
    const texts = eventLog.getSnapshot().map((e) => e.text).reverse()
    expect(texts.some((t) => /^★ rate userId=700008 movieId=296 rating=4\.0 \(eventId=.+\)$/.test(t))).toBe(true)
    expect(texts.some((t) => /^→ Kafka ✓ \(202, eventId=.+\)$/.test(t))).toBe(true)
    expect(texts.some((t) => /^✓ applied \(eventId=.+, batchId=16\)$/.test(t))).toBe(true)
    expect(texts).toContain('phim movieId=296 không còn trong danh sách gợi ý (vừa được rate nên bị loại)')
  })

  it('warns how to load the demo data when the seeded user has no ratings', async () => {
    setup({ seedCount: 0 })
    await userEvent.selectOptions(await screen.findByLabelText('Case test'), 'c2')
    await waitFor(() =>
      expect(eventLog.getSnapshot().some((e) => e.kind === 'err' && e.text.includes('python scripts/seed_demo_users.py'))).toBe(true),
    )
  })

  it('cases 3, 4 and 9 show the demo movie panel, cases 5 and 6 the model lifecycle, others neither', async () => {
    setup()
    const select = await screen.findByLabelText('Case test')
    await userEvent.selectOptions(select, 'c3')
    expect(await screen.findByRole('heading', { name: 'Phim mới (demo-only)' })).toBeInTheDocument()
    await userEvent.selectOptions(select, 'c5')
    expect(await screen.findByRole('heading', { name: 'Vòng đời model (chỉ xem)' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Phim mới (demo-only)' })).not.toBeInTheDocument()
    await userEvent.selectOptions(select, 'c2')
    await screen.findByText('Film 296')
    expect(screen.queryByRole('heading', { name: 'Vòng đời model (chỉ xem)' })).not.toBeInTheDocument()
  })

  it('the free case waits for a userId and loads it on demand', async () => {
    setup()
    expect(await screen.findByText(/Chọn một case test để bắt đầu/)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('userId'), '700008')
    await userEvent.click(screen.getByRole('button', { name: 'Tải gợi ý' }))
    expect(await screen.findByText('Film 296')).toBeInTheDocument()
  })

  it('says so when the typed userId is not a positive number, and loads nothing', async () => {
    const api = setup()
    await userEvent.click(await screen.findByRole('button', { name: 'Tải gợi ý' }))
    expect(screen.getByText('Nhập một userId là số nguyên dương.')).toBeInTheDocument()
    expect(screen.getByLabelText('userId')).toHaveAttribute('aria-invalid', 'true')
    expect(api.callsTo(/^GET \/recommendations/)).toHaveLength(0)
  })

  it('drops the slow answer of a fresh-user search when another case was chosen meanwhile', async () => {
    let releaseFresh: () => void = () => {}
    const gate = new Promise<void>((resolve) => (releaseFresh = resolve))
    installFakeApi([
      ['GET /debug/system', () => ({ status: 200, body: systemStatus() })],
      ['GET /health', () => ({ status: 200, body: { status: 'ok' } })],
      [
        /^GET \/debug\/users\/5\d{5}$/,
        async (req) => {
          await gate
          return { status: 200, body: debugUser(Number(req.path.split('/').pop()), 0) }
        },
      ],
      [/^GET \/debug\/users\/127249$/, () => ({ status: 200, body: debugUser(127249, 69) })],
      [/^GET \/recommendations\/127249/, () => ({ status: 200, body: recommendation(127249, [{ id: 11, rank: 1 }]) })],
      [/^GET \/recommendations\/5\d{5}/, () => ({ status: 200, body: recommendation(500123, [{ id: 22, rank: 1 }], '0_history') })],
    ])
    window.location.hash = '#/cases'
    render(
      <Providers>
        <App />
      </Providers>,
    )
    const select = await screen.findByLabelText('Case test')
    await userEvent.selectOptions(select, 'c1')           // looking for a fresh user: this call is held back
    await userEvent.selectOptions(select, 'noals')        // the presenter picks a fixed user meanwhile
    await waitFor(() => expect(screen.getByLabelText('userId')).toHaveValue(127249))
    expect(await screen.findByText('Film 11')).toBeInTheDocument()

    releaseFresh()                                         // the slow answer arrives late
    await new Promise((r) => setTimeout(r, 150))
    expect(screen.getByLabelText('userId')).toHaveValue(127249)
    expect(screen.getByText('Film 11')).toBeInTheDocument()
    expect(screen.queryByText('Film 22')).not.toBeInTheDocument()
  })
})
