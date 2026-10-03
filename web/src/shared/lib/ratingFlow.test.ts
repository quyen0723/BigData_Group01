import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ApiResult } from '../api/client'
import { createRetryIds } from './retry'
import { RatingFlow, type RatingEvent } from './ratingFlow'

const ok = <T,>(status: number, body: T): ApiResult<T> => ({ ok: status >= 200 && status < 300, status, body })

function setup(overrides: { post?: ReturnType<typeof vi.fn>; status?: ReturnType<typeof vi.fn>; seconds?: number } = {}) {
  const events: RatingEvent[] = []
  let n = 0
  const retry = createRetryIds(() => `ev-${++n}`)
  const post = overrides.post ?? vi.fn(async () => ok(202, { eventId: 'x', status: 'accepted' }))
  const status = overrides.status ?? vi.fn(async () => ok(200, { eventId: 'x', status: 'pending' }))
  const flow = new RatingFlow({
    userId: 7,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    api: { postRating: post as any, ratingStatus: status as any },
    retry,
    pollSeconds: () => overrides.seconds ?? 5,
    onEvent: (e) => events.push(e),
  })
  return { flow, events, post, status, retry }
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('RatingFlow', () => {
  it('locks the movie while the rating is sent and updated, then reports applied', async () => {
    const status = vi
      .fn()
      .mockResolvedValueOnce(ok(200, { eventId: 'ev-1', status: 'pending' }))
      .mockResolvedValueOnce(ok(200, { eventId: 'ev-1', status: 'applied', batchId: 4 }))
    const { flow, events } = setup({ status })

    const done = flow.rate(296, 4)
    expect(flow.getSnapshot().get(296)).toMatchObject({ stars: 4, phase: 'sending' })
    await done
    expect(flow.getSnapshot().get(296)).toMatchObject({ phase: 'updating' })

    await vi.advanceTimersByTimeAsync(1000)
    expect(flow.isPending(296)).toBe(false)
    expect(events.map((e) => e.type)).toEqual(['sending', 'accepted', 'applied'])
    expect(events.at(-1)).toMatchObject({ type: 'applied', movieId: 296, batchId: 4 })
  })

  it('does not send a second rating for a movie that is already in flight', async () => {
    const { flow, post } = setup()
    await flow.rate(296, 4)
    await flow.rate(296, 5)
    expect(post).toHaveBeenCalledTimes(1)
  })

  it('keeps different movies locked independently of each other', async () => {
    const { flow } = setup()
    await flow.rate(296, 4)
    await flow.rate(318, 3)
    expect([...flow.getSnapshot().keys()].sort()).toEqual([296, 318])
  })

  it('unlocks and reports a failure on a non-202 answer, keeping the id for a retry', async () => {
    const post = vi.fn().mockResolvedValueOnce(ok(503, { detail: 'kafka delivery timed out; retry with the same eventId' }))
    const { flow, events, retry } = setup({ post })
    await flow.rate(296, 4)

    expect(flow.isPending(296)).toBe(false)
    expect(events.at(-1)).toMatchObject({ type: 'failed', status: 503, detail: expect.stringContaining('same eventId') })
    expect(retry.size()).toBe(1)                       // 503 is not a final answer

    post.mockResolvedValueOnce(ok(202, { eventId: 'ev-1', status: 'accepted' }))
    await flow.rate(296, 4)
    expect(post.mock.calls[1]![0].eventId).toBe(post.mock.calls[0]![0].eventId)
  })

  it('treats a network error (status 0) as retryable with the same id', async () => {
    const post = vi.fn().mockResolvedValueOnce(ok(0, {})).mockResolvedValueOnce(ok(202, { eventId: 'ev-1', status: 'accepted' }))
    const { flow, retry } = setup({ post })
    await flow.rate(296, 4)
    expect(retry.size()).toBe(1)
    await flow.rate(296, 4)
    expect(post.mock.calls[1]![0].eventId).toBe(post.mock.calls[0]![0].eventId)
  })

  it('forgets every id of the movie after a 202, so a later rating at other stars is a new one', async () => {
    const post = vi
      .fn()
      .mockResolvedValueOnce(ok(503, {}))                                          // 4 stars: unknown outcome, id kept
      .mockResolvedValueOnce(ok(202, { eventId: 'x', status: 'accepted' }))        // 5 stars accepted: final answer
      .mockResolvedValueOnce(ok(202, { eventId: 'x', status: 'accepted' }))        // 4 stars again
    const status = vi.fn(async () => ok(200, { eventId: 'x', status: 'applied', batchId: 1 }))
    const { flow } = setup({ post, status })

    await flow.rate(296, 4)
    await flow.rate(296, 5)
    await vi.advanceTimersByTimeAsync(0)
    await flow.rate(296, 4)

    const ids = post.mock.calls.map((c) => c[0].eventId)
    expect(ids[2]).not.toBe(ids[0])
  })

  it('reports a timeout and unlocks after the configured wait', async () => {
    const { flow, events } = setup({ seconds: 3 })
    await flow.rate(296, 4)
    await vi.advanceTimersByTimeAsync(5000)
    expect(flow.isPending(296)).toBe(false)
    expect(events.at(-1)).toMatchObject({ type: 'timeout', seconds: 3 })
  })

  it('keeps the pending state when the same flow is read after other changes (snapshots are immutable)', async () => {
    const { flow } = setup()
    await flow.rate(296, 4)
    const before = flow.getSnapshot()
    await flow.rate(318, 2)
    expect(before.has(318)).toBe(false)
    expect(flow.getSnapshot()).not.toBe(before)
  })

  it('notifies subscribers when the pending set changes', async () => {
    const { flow } = setup()
    const listener = vi.fn()
    flow.subscribe(listener)
    await flow.rate(296, 4)
    expect(listener).toHaveBeenCalled()
  })

  it('stops polling and ignores late answers after dispose (logout or account switch)', async () => {
    const { flow, status, events } = setup()
    await flow.rate(296, 4)
    const calls = status.mock.calls.length
    flow.dispose()
    await vi.advanceTimersByTimeAsync(5000)
    expect(status.mock.calls.length).toBe(calls)
    expect(events.map((e) => e.type)).toEqual(['sending', 'accepted'])
    await flow.rate(318, 4)                                                       // a disposed flow sends nothing
    expect(events).toHaveLength(2)
  })
})
