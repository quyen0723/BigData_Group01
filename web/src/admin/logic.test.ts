import { describe, expect, it } from 'vitest'
import type { Recommendation } from '@/shared/api/types'
import { CASES, caseById, SEED_USER } from './caseData'
import { diffRecs } from './diff'
import { EventLog, timeLabel } from './eventLog'
import { hrefFor, parseHash } from './route'

const rec = (movieId: number, rank: number, source = 'content', title = `Film ${movieId}`): Recommendation => ({
  movieId,
  title,
  genres: 'Drama',
  rank,
  score: 0.01,
  source,
})

describe('cases', () => {
  it('has the 12 cases of the old page in the same order', () => {
    expect(CASES.map((c) => c.id)).toEqual(['free', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7', 'c8', 'c9', 'als', 'noals'])
  })

  it('keeps who each case runs on: fresh, the seeded user, or a fixed id', () => {
    expect(caseById('c1').user).toBe('fresh')
    expect(caseById('c7').user).toBe('fresh')
    expect(caseById('c2').user).toBe('seed')
    expect(caseById('als').user).toBe(1)
    expect(caseById('noals').user).toBe(127249)
    expect(caseById('free').user).toBeNull()
    expect(SEED_USER).toBe(700008)
  })

  it('shows the movie panel for cases 3, 4 and 9 and the system panel for 5 and 6', () => {
    expect(CASES.filter((c) => c.movies).map((c) => c.id)).toEqual(['c3', 'c4', 'c9'])
    expect(CASES.filter((c) => c.kind === 'system').map((c) => c.id)).toEqual(['c5', 'c6'])
  })

  it('has the five table cells on every case and uses no emoji', () => {
    for (const c of CASES) {
      for (const key of ['what', 'rec', 'streaming', 'retrain', 'chot'] as const) expect(c[key].length, `${c.id}.${key}`).toBeGreaterThan(0)
      expect(JSON.stringify(c), c.id).not.toMatch(/\p{Extended_Pictographic}/u)
    }
  })

  it('says that popularity uses the weighted rating in case 1', () => {
    expect(caseById('c1').decision).toMatch(/weighted rating/)
    expect(caseById('c1').decision).not.toMatch(/điểm trung bình thô/)
  })

  it('falls back to the free case for an unknown id', () => {
    expect(caseById('nope').id).toBe('free')
  })
})

describe('route', () => {
  it('opens the section named by the hash', () => {
    expect(parseHash('#/cases')).toEqual({ section: 'cases', userId: null })
    expect(parseHash('#/movies')).toEqual({ section: 'movies', userId: null })
    expect(parseHash('#/models')).toEqual({ section: 'models', userId: null })
    expect(parseHash('#/log')).toEqual({ section: 'log', userId: null })
  })

  it('reads the user id of #/users/<id>', () => {
    expect(parseHash('#/users/591751')).toEqual({ section: 'users', userId: 591751 })
    expect(parseHash('#/users')).toEqual({ section: 'users', userId: null })
    expect(parseHash('#/users/abc')).toEqual({ section: 'users', userId: null })
    expect(parseHash('#/users/-4')).toEqual({ section: 'users', userId: null })
  })

  it('opens the overview for an empty or unknown hash', () => {
    for (const h of ['', '#', '#/', '#/nope', '#/users/5/extra/9x'.replace('users', 'nope')]) {
      expect(parseHash(h).section, h).toBe('overview')
    }
  })

  it('builds the hash of a section', () => {
    expect(hrefFor('cases')).toBe('#/cases')
    expect(hrefFor('users', 591751)).toBe('#/users/591751')
    expect(hrefFor('users')).toBe('#/users')
  })
})

describe('diffRecs', () => {
  it('reports a tier change', () => {
    const lines = diffRecs({ tier: '0_history', movieIds: [1] }, { tier: 'few_history', recommendations: [rec(1, 1)] }, new Set())
    expect(lines.map((l) => l.text)).toEqual(['tier đổi: 0_history → few_history'])
  })

  it('names a movie that left the list because it was rated, and counts the ones pushed out', () => {
    const lines = diffRecs(
      { tier: 'few_history', movieIds: [1, 2, 3] },
      { tier: 'few_history', recommendations: [rec(3, 1), rec(9, 2)] },
      new Set([1]),
    )
    expect(lines.map((l) => l.text)).toEqual([
      'phim movieId=1 không còn trong danh sách gợi ý (vừa được rate nên bị loại)',
      '1 phim khác không còn trong top-k (bị đẩy ra do thứ hạng thay đổi)',
    ])
  })

  it('announces a new movie with its rank', () => {
    const lines = diffRecs(
      { tier: 'few_history', movieIds: [1, 2] },
      { tier: 'few_history', recommendations: [rec(1, 1), rec(2, 2), rec(9000001, 3, 'new', 'Demo Crime Story')] },
      new Set(),
    )
    expect(lines.map((l) => l.text)).toEqual(['phim MỚI movieId=9000001 (Demo Crime Story) xuất hiện ở hạng 3'])
  })

  it('does not announce a new movie that was already there', () => {
    expect(
      diffRecs({ tier: 'a', movieIds: [9000001] }, { tier: 'a', recommendations: [rec(9000001, 3, 'new')] }, new Set()),
    ).toEqual([])
  })

  it('says nothing when nothing changed', () => {
    expect(diffRecs({ tier: 'a', movieIds: [1] }, { tier: 'a', recommendations: [rec(1, 1)] }, new Set())).toEqual([])
  })
})

function memoryStorage(): Storage {
  const m = new Map<string, string>()
  return {
    get length() {
      return m.size
    },
    clear: () => m.clear(),
    getItem: (k) => m.get(k) ?? null,
    key: (i) => [...m.keys()][i] ?? null,
    removeItem: (k) => void m.delete(k),
    setItem: (k, v) => void m.set(k, v),
  }
}

describe('EventLog', () => {
  const at = (h: number, m: number, s: number, ms: number) => () => new Date(2026, 9, 3, h, m, s, ms)

  it('formats times as hh:mm:ss.mmm', () => {
    expect(timeLabel(new Date(2026, 9, 3, 9, 5, 7, 42))).toBe('09:05:07.042')
  })

  it('keeps the newest entry first, with its time and kind', () => {
    const log = new EventLog(() => memoryStorage(), at(10, 0, 0, 1))
    log.add('first')
    log.add('second', 'ok')
    log.add('third', 'err')
    expect(log.getSnapshot().map((e) => [e.text, e.kind])).toEqual([['third', 'err'], ['second', 'ok'], ['first', 'info']])
    expect(log.getSnapshot()[0]!.time).toBe('10:00:00.001')
  })

  it('survives a reload through sessionStorage and goes on numbering', () => {
    const storage = memoryStorage()
    const a = new EventLog(() => storage)
    a.add('one')
    a.add('two')
    const b = new EventLog(() => storage)
    expect(b.getSnapshot().map((e) => e.text)).toEqual(['two', 'one'])
    b.add('three')
    expect(new Set(b.getSnapshot().map((e) => e.id)).size).toBe(3)
  })

  it('works when storage throws or holds junk', () => {
    const boom: Storage = { ...memoryStorage(), getItem: () => { throw new Error('x') }, setItem: () => { throw new Error('x') } }
    const log = new EventLog(() => boom)
    expect(() => log.add('still here')).not.toThrow()
    expect(log.getSnapshot()).toHaveLength(1)
    const junk = memoryStorage()
    junk.setItem('mladmin.log', '{"not":"an array"}')
    expect(new EventLog(() => junk).getSnapshot()).toEqual([])
  })

  it('drops stored entries that are not complete log lines, including one with an unknown kind', () => {
    const storage = memoryStorage()
    storage.setItem(
      'mladmin.log',
      JSON.stringify([
        { id: 3, time: '10:00:00.000', text: 'good', kind: 'ok' },
        { id: 2, time: '10:00:00.000', text: 'no kind' },
        { id: 1, time: '10:00:00.000', text: 'bad kind', kind: 'weird' },
        'junk',
        null,
      ]),
    )
    const log = new EventLog(() => storage)
    expect(log.getSnapshot().map((e) => e.text)).toEqual(['good'])
  })

  it('is capped and can be cleared, notifying subscribers', () => {
    const log = new EventLog(() => memoryStorage())
    let calls = 0
    log.subscribe(() => calls++)
    for (let i = 0; i < 350; i++) log.add(`e${i}`)
    expect(log.getSnapshot()).toHaveLength(300)
    expect(log.getSnapshot()[0]!.text).toBe('e349')
    log.clear()
    expect(log.getSnapshot()).toEqual([])
    expect(calls).toBe(351)
  })
})
