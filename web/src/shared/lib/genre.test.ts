import { describe, expect, it } from 'vitest'
import colors from './genre-colors.json'
import { familyColors, GENRES, genreInfo } from './genre'

// The 19 MovieLens genres of the API (MOVIELENS_GENRES in src/api/main.py) plus the placeholder.
const MOVIELENS = [
  'Action', 'Adventure', 'Animation', 'Children', 'Comedy', 'Crime', 'Documentary', 'Drama', 'Fantasy', 'Film-Noir',
  'Horror', 'IMAX', 'Musical', 'Mystery', 'Romance', 'Sci-Fi', 'Thriller', 'War', 'Western',
]

describe('genre tiles', () => {
  it('covers all 19 genres and the placeholder, each with a family, an icon and a Vietnamese label', () => {
    for (const g of [...MOVIELENS, '(no genres listed)']) {
      const info = GENRES[g]
      expect(info, g).toBeDefined()
      expect(info!.icon, g).toBeTruthy()
      expect(info!.label.length, g).toBeGreaterThan(0)
      expect(colors[info!.family], g).toBeDefined()
    }
    expect(Object.keys(GENRES)).toHaveLength(20)
  })

  it('groups the 19 genres into the 8 colour families of the design', () => {
    const families = new Set(MOVIELENS.map((g) => GENRES[g]!.family))
    expect(families.size).toBe(8)
  })

  it('gives every family a tile fill and a text colour', () => {
    for (const family of new Set(Object.values(GENRES).map((g) => g.family))) {
      const c = familyColors(family)
      expect(c.bg).toMatch(/^#[0-9a-f]{6}$/)
      expect(c.fg).toMatch(/^#[0-9a-f]{6}$/)
    }
  })

  it('uses the placeholder tile for a genre it does not know', () => {
    expect(genreInfo('Made-up')).toBe(GENRES['(no genres listed)'])
  })
})
