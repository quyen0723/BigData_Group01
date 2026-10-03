import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { installFakeApi, type FakeReply } from '@/test/fakeApi'
import type { RatingEvent } from '../lib/ratingFlow'
import { useRatingFlow } from './useRatingFlow'

afterEach(() => vi.unstubAllGlobals())

type Props = { userId: number | null; pollSeconds?: number; onEvent?: (e: RatingEvent) => void }

function mount(post: (userId: number, eventId: string) => FakeReply, status: () => FakeReply) {
  const api = installFakeApi([
    ['POST /ratings', (req) => post((req.body as { userId: number }).userId, (req.body as { eventId: string }).eventId)],
    [/^GET \/ratings\/[^/]+$/, () => status()],
  ])
  const first = vi.fn()
  const hook = renderHook((p: Props) => useRatingFlow(p.userId, { pollSeconds: p.pollSeconds ?? 60, onEvent: p.onEvent ?? first }), {
    initialProps: { userId: 7 } as Props,
  })
  return { api, hook, first }
}

const accepted = (_u: number, eventId: string): FakeReply => ({ status: 202, body: { eventId, status: 'accepted' } })
const pendingStatus = (): FakeReply => ({ status: 200, body: { eventId: 'x', status: 'pending' } })
const appliedStatus = (): FakeReply => ({ status: 200, body: { eventId: 'x', status: 'applied', batchId: 9, ingestedAt: 'now' } })

describe('useRatingFlow', () => {
  it('sends the rating for the current user, locks the movie and reports each step to onEvent', async () => {
    const { api, hook, first } = mount(accepted, appliedStatus)
    await act(async () => {
      await hook.result.current.rate(296, 4)
    })

    expect(api.callsTo('POST /ratings')[0]!.body).toMatchObject({ userId: 7, movieId: 296, rating: 4 })
    await waitFor(() => expect(first.mock.calls.map(([e]) => (e as RatingEvent).type)).toEqual(['sending', 'accepted', 'applied']))
    expect(hook.result.current.pending.size).toBe(0)       // applied: the lock is gone
  })

  it('does nothing for a signed-out page (no user)', async () => {
    const { api, hook } = mount(accepted, appliedStatus)
    hook.rerender({ userId: null })
    await act(async () => {
      await hook.result.current.rate(296, 4)
    })
    expect(api.callsTo('POST /ratings')).toHaveLength(0)
    expect(hook.result.current.pending.size).toBe(0)
  })

  it('stops polling and forgets the retry ids when the account changes', async () => {
    const sentIds: string[] = []
    const { api, hook, first } = mount(
      (u, id) => {
        sentIds.push(`${u}:${id}`)
        return sentIds.length === 1 ? { status: 503, body: { detail: 'kafka delivery timed out' } } : accepted(u, id)
      },
      pendingStatus,
    )
    await act(async () => {
      await hook.result.current.rate(296, 4)                // 503: unknown outcome, so the id is kept for a retry
    })
    await act(async () => {
      await hook.result.current.rate(318, 3)                // 202: starts polling, never applied
    })
    await waitFor(() => expect(api.callsTo(/^GET \/ratings\//).length).toBeGreaterThan(0))
    expect(hook.result.current.pending.has(318)).toBe(true)

    hook.rerender({ userId: 8 })                            // another account signs in on this page
    await waitFor(() => expect(hook.result.current.pending.size).toBe(0))
    const pollsAtSwitch = api.callsTo(/^GET \/ratings\//).length
    await new Promise((r) => setTimeout(r, 1300))           // longer than the 1 s poll interval
    expect(api.callsTo(/^GET \/ratings\//)).toHaveLength(pollsAtSwitch)

    hook.rerender({ userId: 7 })                            // and the first one comes back
    await act(async () => {
      await hook.result.current.rate(296, 4)
    })
    const ids = api.callsTo('POST /ratings').map((c) => (c.body as { eventId: string }).eventId)
    expect(ids).toHaveLength(3)
    expect(ids[2]).not.toBe(ids[0])                         // the id kept after the 503 was cleared with the old flow
    expect(first.mock.calls.some(([e]) => (e as RatingEvent).type === 'timeout')).toBe(false)
  })

  it('keeps the same flow when only onEvent or pollSeconds change', async () => {
    const { api, hook, first } = mount(accepted, pendingStatus)
    await act(async () => {
      await hook.result.current.rate(296, 4)
    })
    expect(hook.result.current.pending.get(296)).toMatchObject({ stars: 4, phase: 'updating' })

    const second = vi.fn()
    hook.rerender({ userId: 7, pollSeconds: 90, onEvent: second })
    expect(hook.result.current.pending.get(296)).toMatchObject({ stars: 4, phase: 'updating' })   // still locked: same flow
    expect(api.callsTo('POST /ratings')).toHaveLength(1)

    api.calls.length = 0
    await act(async () => {
      await hook.result.current.rate(318, 5)                // a new rating reports to the new onEvent
    })
    expect(second.mock.calls.map(([e]) => (e as RatingEvent).type)).toContain('sending')
    expect(first.mock.calls.filter(([e]) => (e as RatingEvent).movieId === 318)).toHaveLength(0)
  })
})
