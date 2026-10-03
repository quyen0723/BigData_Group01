import { describe, expect, it } from 'vitest'
import { pickFreshUser } from './freshUser'
import { TITLE_MAX, validateMovie } from './movieForm'

describe('validateMovie', () => {
  it('needs a title and at least one genre', () => {
    expect(validateMovie('', [])).toEqual({ ok: false, errors: { title: 'Vui lòng nhập tên phim.', genres: 'Chọn ít nhất một thể loại.' } })
    expect(validateMovie('   ', ['Crime'])).toMatchObject({ ok: false, errors: { title: 'Vui lòng nhập tên phim.' } })
    expect(validateMovie('Demo', [])).toMatchObject({ ok: false, errors: { genres: 'Chọn ít nhất một thể loại.' } })
  })

  it('accepts a trimmed title with genres', () => {
    expect(validateMovie('  Demo Crime Story ', ['Crime', 'Drama'])).toEqual({ ok: true, title: 'Demo Crime Story' })
  })

  it('refuses a title over the limit', () => {
    expect(validateMovie('x'.repeat(TITLE_MAX + 1), ['Crime']).ok).toBe(false)
    expect(validateMovie('x'.repeat(TITLE_MAX), ['Crime']).ok).toBe(true)
  })
})

describe('pickFreshUser (admin)', () => {
  it('returns the first id without history', async () => {
    const asked: number[] = []
    const id = await pickFreshUser({ hasHistory: async (u) => (asked.push(u), asked.length < 3), rand: () => 0.25 })
    expect(asked).toHaveLength(3)
    expect(id).toBe(asked[2])
    expect(id).toBeGreaterThanOrEqual(500000)
  })

  it('after 5 tries returns the last id drawn, like the old page', async () => {
    const asked: number[] = []
    let n = 0
    const id = await pickFreshUser({ hasHistory: async (u) => (asked.push(u), true), rand: () => (n++ % 7) / 10 })
    expect(asked).toHaveLength(5)
    expect(id).toBe(asked[4])
  })
})
