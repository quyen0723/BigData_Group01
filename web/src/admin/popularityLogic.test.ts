import { describe, expect, it } from 'vitest'
import type { PopularityItem } from '@/shared/api/types'
import { formulaSteps, moveText, parseM, rankMap, rankMoves, trustText, versusBaseline } from './popularityLogic'

const item = (movieId: number, rank: number, over: Partial<PopularityItem> = {}): PopularityItem => ({
  rank,
  movieId,
  title: `Film ${movieId}`,
  genres: 'Drama',
  avgRating: 4.2,
  support: 1000,
  baseSupport: 1000,
  newRatings: 0,
  wr: 3.86,
  baseRank: rank,
  ...over,
})

describe('parseM', () => {
  it('empty means "use the configured m"', () => expect(parseM('  ')).toEqual({ value: null, invalid: false }))
  it('accepts 0 up to 100000, with decimals', () => {
    expect(parseM('0')).toEqual({ value: 0, invalid: false })
    expect(parseM('250.5')).toEqual({ value: 250.5, invalid: false })
    expect(parseM('100000')).toEqual({ value: 100000, invalid: false })
  })
  it('refuses negatives, too large values and words', () => {
    for (const bad of ['-1', '100001', 'abc', '1e999', 'NaN']) expect(parseM(bad)).toEqual({ value: null, invalid: true })
  })
})

describe('rank moves between two refreshes', () => {
  it('marks only the movies whose rank changed, positive = up', () => {
    const before = rankMap([item(1, 1), item(2, 2), item(3, 3), item(4, 4)])
    const after = [item(1, 1), item(3, 2), item(2, 3), item(4, 4)]
    expect(rankMoves(before, after)).toEqual(new Map([[3, 1], [2, -1]]))
  })
  it('a movie that was not in the previous list is not a move', () => {
    expect(rankMoves(rankMap([item(1, 1)]), [item(1, 1), item(9, 2)]).size).toBe(0)
  })
  it('says the move in words', () => {
    expect(moveText(1)).toBe('lên 1')
    expect(moveText(-2)).toBe('xuống 2')
  })
})

describe('versusBaseline', () => {
  it('is the persistent comparison with the offline list', () => {
    expect(versusBaseline(item(1, 8, { baseRank: 9 }))).toEqual({ delta: 1, text: 'lên 1 so với gốc #9' })
    expect(versusBaseline(item(1, 9, { baseRank: 8 }))).toEqual({ delta: -1, text: 'xuống 1 so với gốc #8' })
    expect(versusBaseline(item(1, 3, { baseRank: 3 }))).toEqual({ delta: 0, text: 'giữ hạng gốc #3' })
    expect(versusBaseline(item(1, 3, { baseRank: null })).delta).toBeNull()
  })
})

describe('formula', () => {
  it('substitutes the numbers and reproduces the WR the API sent (Planet Earth)', () => {
    const planet = item(1, 9, { avgRating: 4.468, support: 173, wr: 3.667 })
    const f = formulaSteps(planet, 1000, 3.5287)!
    expect(f.w).toBeCloseTo(173 / 1173, 12)
    expect(f.wr).toBeCloseTo(3.667, 3)
  })
  it('Shawshank keeps almost all of its own average', () => {
    const f = formulaSteps(item(1, 1, { avgRating: 4.4282, support: 73954 }), 1000, 3.5287)!
    expect(Math.round(f.w * 100)).toBe(99)
    expect(f.wr).toBeCloseTo(4.4162, 3)
  })
  it('m = 0 keeps the whole average', () => {
    const f = formulaSteps(item(1, 1, { avgRating: 4.5 }), 0, 3.5)!
    expect(f.w).toBe(1)
    expect(f.wr).toBe(4.5)
  })
  it('has no steps when the artifact gave no average', () => {
    expect(formulaSteps(item(1, 1, { avgRating: null }), 1000, 3.5)).toBeNull()
  })
  it('says the weight in whole percentages that add up to 100', () => {
    expect(trustText(0.927)).toBe('Phim này được tin 93% điểm riêng của nó, 7% bị kéo về điểm trung bình chung.')
    expect(trustText(0.147)).toBe('Phim này được tin 15% điểm riêng của nó, 85% bị kéo về điểm trung bình chung.')
  })
})
