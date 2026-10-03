import { describe, expect, it } from 'vitest'
import type { Recommendation } from '../api/types'
import { isNew, layoutFeed, primarySource, reasonOf, SOURCE_TITLES, sourcesOf } from './sources'

const rec = (rank: number, source: string, movieId = rank): Recommendation => ({
  movieId,
  title: `Movie ${movieId}`,
  genres: 'Drama',
  rank,
  score: 1 / (60 + rank),
  source,
})

describe('primarySource', () => {
  it('takes the first of new, als, content, popularity found in the label', () => {
    expect(primarySource(rec(1, 'als'))).toBe('als')
    expect(primarySource(rec(1, 'content'))).toBe('content')
    expect(primarySource(rec(1, 'popularity'))).toBe('popularity')
    expect(primarySource(rec(1, 'new'))).toBe('new')
  })

  it('handles combined labels such as als+content', () => {
    expect(primarySource(rec(1, 'als+content'))).toBe('als')
    expect(primarySource(rec(1, 'content+popularity'))).toBe('content')
    expect(primarySource(rec(1, 'popularity+als'))).toBe('als')
  })

  it('falls back to popularity for an unknown label', () => {
    expect(primarySource(rec(1, 'something-else'))).toBe('popularity')
    expect(sourcesOf(rec(1, 'something-else'))).toEqual([])
  })
})

describe('reasonOf and isNew', () => {
  it('uses the user-language title of the primary source', () => {
    expect(reasonOf(rec(1, 'als+content'))).toBe('Dành riêng cho bạn')
    expect(reasonOf(rec(1, 'content'))).toBe('Giống phim bạn đã thích')
    expect(reasonOf(rec(1, 'new'))).toBe('Mới thêm')
    expect(reasonOf(rec(1, 'popularity'))).toBe('Đang được yêu thích')
  })

  it('shows no technical word on the user page', () => {
    for (const title of Object.values(SOURCE_TITLES)) expect(title).not.toMatch(/als|content|popularity|tier|strategy/i)
  })

  it('flags new movies only', () => {
    expect(isNew(rec(1, 'new'))).toBe(true)
    expect(isNew(rec(1, 'content'))).toBe(false)
  })
})

describe('layoutFeed', () => {
  it('is empty for no recommendations', () => {
    expect(layoutFeed([])).toEqual({ kind: 'empty' })
  })

  it('shows a single grid when all items share one source', () => {
    const items = [1, 2, 3].map((r) => rec(r, 'content'))
    const layout = layoutFeed(items)
    expect(layout.kind).toBe('grid')
    if (layout.kind === 'grid') {
      expect(layout.title).toBe('Giống phim bạn đã thích')
      expect(layout.items.map((i) => i.rank)).toEqual([1, 2, 3])
    }
  })

  it('shows a single grid when combined labels collapse to one source', () => {
    const layout = layoutFeed([rec(1, 'als+content'), rec(2, 'als')])
    expect(layout.kind).toBe('grid')
  })

  it('splits into rows when two sources are present, each card keeping its original rank', () => {
    const items = [rec(1, 'als'), rec(2, 'als'), rec(3, 'als'), ...[4, 5, 6, 7, 8, 9, 10].map((r) => rec(r, 'content'))]
    const layout = layoutFeed(items)
    expect(layout.kind).toBe('rows')
    if (layout.kind === 'rows') {
      expect(layout.rows.map((r) => r.title)).toEqual(['Dành riêng cho bạn', 'Giống phim bạn đã thích'])
      expect(layout.rows[0]!.items.map((i) => i.rank)).toEqual([1, 2, 3])
      expect(layout.rows[1]!.items.map((i) => i.rank)).toEqual([4, 5, 6, 7, 8, 9, 10])
    }
  })

  it('orders rows by the best rank inside each row', () => {
    const items = [rec(1, 'content'), rec(2, 'content'), rec(3, 'new'), rec(4, 'popularity')]
    const layout = layoutFeed(items)
    expect(layout.kind).toBe('rows')
    if (layout.kind === 'rows') expect(layout.rows.map((r) => r.source)).toEqual(['content', 'new', 'popularity'])
  })

  it('places a new movie in its own row when others share a source', () => {
    const layout = layoutFeed([rec(1, 'content'), rec(2, 'content'), rec(3, 'new'), rec(4, 'content')])
    expect(layout.kind).toBe('rows')
    if (layout.kind === 'rows') {
      const row = layout.rows.find((r) => r.source === 'new')!
      expect(row.items.map((i) => i.rank)).toEqual([3])
    }
  })
})
