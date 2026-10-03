import { describe, expect, it } from 'vitest'
import { bannerFor } from './tier'

const T = 10

describe('bannerFor', () => {
  it('no ratings: popular movies, progress 0 of T', () => {
    const b = bannerFor({ tier: '0_history', fallbackReason: null, rated: 0, threshold: T })
    expect(b.text).toContain('chưa chấm phim nào')
    expect(b.text).toContain('được nhiều người đánh giá cao')
    expect(b.progress).toEqual({ value: 0, max: T })
  })

  it('few ratings: says how many were rated and how many more unlock personal suggestions', () => {
    const b = bannerFor({ tier: 'few_history', fallbackReason: null, rated: 2, threshold: T })
    expect(b.text).toContain('Bạn đã chấm 2 phim')
    expect(b.text).toContain('giống phim bạn thích')
    expect(b.text).toContain('Chấm thêm 8 phim')
    expect(b.progress).toEqual({ value: 2, max: T })
  })

  it('enough ratings: learned from the ratings and similar viewers, no progress bar', () => {
    const b = bannerFor({ tier: 'enough_history', fallbackReason: null, rated: 149, threshold: T })
    expect(b.text).toContain('149 phim')
    expect(b.text).toContain('người có gu giống bạn')
    expect(b.progress).toBeNull()
  })

  it('als_artifact_missing: no personal profile yet, without technical words', () => {
    const b = bannerFor({ tier: 'enough_history', fallbackReason: 'als_artifact_missing', rated: 70, threshold: T })
    expect(b.text).toContain('Bạn đã chấm 70 phim')
    expect(b.text).toContain('chưa có hồ sơ riêng')
    expect(b.text).toContain('giống phim bạn thích')
    expect(b.progress).toBeNull()
  })

  it('no_content_candidates: falls back to popular movies and keeps the tier progress', () => {
    const b = bannerFor({ tier: 'few_history', fallbackReason: 'no_content_candidates', rated: 3, threshold: T })
    expect(b.text).toContain('Chưa tìm được phim giống phim bạn thích')
    expect(b.progress).toEqual({ value: 3, max: T })
  })

  it('filled_from_popularity: keeps the tier text and adds a second sentence', () => {
    const b = bannerFor({ tier: 'few_history', fallbackReason: 'filled_from_popularity', rated: 4, threshold: T })
    expect(b.text).toContain('Bạn đã chấm 4 phim')
    expect(b.extra).toContain('phim phổ biến')
  })

  it('never shows more progress than the threshold or a negative number left', () => {
    const b = bannerFor({ tier: 'few_history', fallbackReason: null, rated: 12, threshold: T })
    expect(b.progress).toEqual({ value: T, max: T })
    expect(b.text).toContain('Chấm thêm 0 phim')
  })

  it('uses no technical term in any banner', () => {
    const cases = [
      bannerFor({ tier: '0_history', fallbackReason: null, rated: 0, threshold: T }),
      bannerFor({ tier: 'few_history', fallbackReason: null, rated: 2, threshold: T }),
      bannerFor({ tier: 'enough_history', fallbackReason: null, rated: 50, threshold: T }),
      bannerFor({ tier: 'enough_history', fallbackReason: 'als_artifact_missing', rated: 50, threshold: T }),
      bannerFor({ tier: 'few_history', fallbackReason: 'no_content_candidates', rated: 2, threshold: T }),
      bannerFor({ tier: 'few_history', fallbackReason: 'filled_from_popularity', rated: 2, threshold: T }),
    ]
    for (const b of cases) expect(`${b.text} ${b.extra ?? ''}`).not.toMatch(/tier|strategy|als|fallback|eventId|batch|history/i)
  })
})
