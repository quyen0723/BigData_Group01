import { describe, expect, it } from 'vitest'
import { createRetryIds, isFinalAnswer } from './retry'

function counter() {
  let n = 0
  return () => `id-${++n}`
}

describe('retry ids', () => {
  it('returns the same id for the same user, movie and stars until a final answer', () => {
    const ids = createRetryIds(counter())
    const first = ids.idFor(1, 296, 4)
    expect(ids.idFor(1, 296, 4)).toBe(first)
  })

  it('uses a different id for another star value, another movie or another user', () => {
    const ids = createRetryIds(counter())
    const base = ids.idFor(1, 296, 4)
    expect(ids.idFor(1, 296, 5)).not.toBe(base)
    expect(ids.idFor(1, 318, 4)).not.toBe(base)
    expect(ids.idFor(2, 296, 4)).not.toBe(base)
  })

  it('drops the ids of EVERY star value of a movie after a final answer', () => {
    // 4 stars -> 503 keeps E1; 5 stars -> 202 forgets the movie; 4 stars again must NOT reuse E1,
    // otherwise the ledger would swallow the new rating (review finding, design D-3).
    const ids = createRetryIds(counter())
    const e1 = ids.idFor(1, 296, 4)
    ids.idFor(1, 296, 5)
    ids.forget(1, 296)
    expect(ids.idFor(1, 296, 4)).not.toBe(e1)
  })

  it('leaves the ids of other movies and users alone when one movie is forgotten', () => {
    const ids = createRetryIds(counter())
    const other = ids.idFor(1, 318, 3)
    const otherUser = ids.idFor(2, 296, 3)
    ids.forget(1, 296)
    expect(ids.idFor(1, 318, 3)).toBe(other)
    expect(ids.idFor(2, 296, 3)).toBe(otherUser)
  })

  it('does not mix up a movie id that is a prefix of another (29 vs 296)', () => {
    const ids = createRetryIds(counter())
    const long = ids.idFor(1, 296, 4)
    ids.forget(1, 29)
    expect(ids.idFor(1, 296, 4)).toBe(long)
  })

  it('clears everything on login or logout', () => {
    const ids = createRetryIds(counter())
    ids.idFor(1, 296, 4)
    ids.idFor(1, 318, 5)
    ids.clear()
    expect(ids.size()).toBe(0)
  })

  it('treats 202 and 422 as final, anything else as retryable', () => {
    expect(isFinalAnswer(202)).toBe(true)
    expect(isFinalAnswer(422)).toBe(true)
    for (const status of [0, 500, 503, 404, 200]) expect(isFinalAnswer(status), String(status)).toBe(false)
  })
})
