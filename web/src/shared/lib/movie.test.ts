import { describe, expect, it } from 'vitest'
import { primaryGenre, splitGenres, splitYear } from './movie'

describe('splitYear', () => {
  it('takes a trailing (YYYY) out of the title', () => {
    expect(splitYear('Pulp Fiction (1994)')).toEqual({ title: 'Pulp Fiction', year: 1994 })
    expect(splitYear('Seven Samurai (Shichinin no samurai) (1954)')).toEqual({
      title: 'Seven Samurai (Shichinin no samurai)',
      year: 1954,
    })
  })

  it('leaves a title without a year alone', () => {
    expect(splitYear('Demo Crime Story')).toEqual({ title: 'Demo Crime Story', year: null })
  })

  it('does not take a year from the middle of the title', () => {
    expect(splitYear('2001: A Space Odyssey')).toEqual({ title: '2001: A Space Odyssey', year: null })
    expect(splitYear('Blade Runner (1982) Director Cut')).toEqual({ title: 'Blade Runner (1982) Director Cut', year: null })
  })

  it('ignores parentheses that are not a 4-digit year', () => {
    expect(splitYear('Heat (95)')).toEqual({ title: 'Heat (95)', year: null })
  })
})

describe('genres', () => {
  it('splits the MovieLens pipe format', () => {
    expect(splitGenres('Comedy|Crime|Drama|Thriller')).toEqual(['Comedy', 'Crime', 'Drama', 'Thriller'])
    expect(primaryGenre('Comedy|Crime')).toBe('Comedy')
  })

  it('treats "(no genres listed)" and empty strings as no genre', () => {
    expect(splitGenres('(no genres listed)')).toEqual([])
    expect(splitGenres('')).toEqual([])
    expect(primaryGenre('(no genres listed)')).toBe('(no genres listed)')
  })
})
