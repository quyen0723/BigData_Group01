import { describe, expect, it } from 'vitest'
import type { RatingEvent } from '@/shared/lib/ratingFlow'
import { noticeFor } from './events'

const base = { movieId: 296, eventId: 'abc-123' }

describe('noticeFor', () => {
  it('says nothing while the rating is being sent', () => {
    expect(noticeFor({ type: 'sending', ...base, stars: 4 }, 'Pulp Fiction')).toBeNull()
  })

  it('confirms the saved rating with the stars and the movie title', () => {
    const n = noticeFor({ type: 'accepted', ...base, stars: 4 }, 'Pulp Fiction')
    expect(n).toEqual({ kind: 'success', text: 'Đã lưu đánh giá 4 sao cho “Pulp Fiction”' })
  })

  it('reports a failure with a retry offer and without status codes or ids', () => {
    const e: RatingEvent = { type: 'failed', ...base, stars: 4, status: 503, detail: 'kafka delivery timed out; retry with the same eventId' }
    const n = noticeFor(e, 'x')!
    expect(n.kind).toBe('error')
    expect(n.retry).toBe(true)
    expect(n.text).toBe('Chưa lưu được đánh giá. Vui lòng thử lại.')
    expect(n.text).not.toMatch(/503|eventId|kafka|abc-123/i)
  })

  it('reloads the feed and the history when the rating is applied', () => {
    const n = noticeFor({ type: 'applied', ...base, batchId: 4 }, 'x')!
    expect(n).toMatchObject({ kind: 'success', text: 'Gợi ý của bạn đã được cập nhật', refresh: 'all' })
    expect(n.text).not.toMatch(/batch/i)
  })

  it('on timeout says the rating is saved and reloads only the history', () => {
    const n = noticeFor({ type: 'timeout', ...base, seconds: 60 }, 'x')!
    expect(n).toEqual({ kind: 'info', text: 'Đánh giá đã lưu, gợi ý sẽ cập nhật sau.', refresh: 'history' })
  })
})
