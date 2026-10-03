import { describe, expect, it } from 'vitest'
import {
  ACCOUNTS_KEY,
  addCreated,
  clearSession,
  FRESH_ID_BASE,
  FRESH_ID_SPAN,
  pickFreshUserId,
  PERSONAS,
  readCreated,
  readSession,
  safeStore,
  saveSession,
  SESSION_KEY,
  validateName,
} from './account'

function memoryArea(): Storage {
  const data = new Map<string, string>()
  return {
    get length() {
      return data.size
    },
    clear: () => data.clear(),
    getItem: (k) => data.get(k) ?? null,
    key: (i) => [...data.keys()][i] ?? null,
    removeItem: (k) => void data.delete(k),
    setItem: (k, v) => void data.set(k, v),
  }
}

const throwing = (): Storage => {
  const boom = () => {
    throw new Error('storage blocked')
  }
  return { length: 0, clear: boom, getItem: boom, key: boom, removeItem: boom, setItem: boom }
}

describe('personas', () => {
  it('are An 700008, Bình 1 and Chi 127249, described by taste only', () => {
    expect(PERSONAS.map((p) => [p.name, p.userId])).toEqual([['An', 700008], ['Bình', 1], ['Chi', 127249]])
    for (const p of PERSONAS) expect(p.taste).not.toMatch(/tuổi|nam|nữ|giới tính|\d+ tuổi/i)
  })
})

describe('storage', () => {
  it('keeps the session in sessionStorage and created accounts in localStorage under the old keys', () => {
    const areas = { sessionStorage: memoryArea(), localStorage: memoryArea() }
    const store = safeStore((a) => areas[a])
    saveSession(store, { name: 'Minh', userId: 500123 })
    addCreated(store, { name: 'Minh', userId: 500123 })
    expect(JSON.parse(areas.sessionStorage.getItem(SESSION_KEY)!)).toEqual({ name: 'Minh', userId: 500123 })
    expect(JSON.parse(areas.localStorage.getItem(ACCOUNTS_KEY)!)).toEqual([{ name: 'Minh', userId: 500123 }])
    expect(readSession(store)).toEqual({ name: 'Minh', userId: 500123 })
    expect(readCreated(store)).toEqual([{ name: 'Minh', userId: 500123 }])
    clearSession(store)
    expect(readSession(store)).toBeNull()
  })

  it('appends created accounts without losing the earlier ones', () => {
    const areas = { sessionStorage: memoryArea(), localStorage: memoryArea() }
    const store = safeStore((a) => areas[a])
    addCreated(store, { name: 'A', userId: 500001 })
    expect(addCreated(store, { name: 'B', userId: 500002 })).toHaveLength(2)
  })

  it('works without storage: reads give nothing, writes do not throw', () => {
    const store = safeStore(() => throwing())
    expect(readSession(store)).toBeNull()
    expect(readCreated(store)).toEqual([])
    expect(() => saveSession(store, { name: 'x', userId: 1 })).not.toThrow()
    expect(() => addCreated(store, { name: 'x', userId: 1 })).not.toThrow()
    expect(() => clearSession(store)).not.toThrow()
  })

  it('ignores stored values that are not accounts', () => {
    const areas = { sessionStorage: memoryArea(), localStorage: memoryArea() }
    areas.sessionStorage.setItem(SESSION_KEY, '{"name":5}')
    areas.localStorage.setItem(ACCOUNTS_KEY, '[{"name":"ok","userId":7},{"x":1},"junk"]')
    const store = safeStore((a) => areas[a])
    expect(readSession(store)).toBeNull()
    expect(readCreated(store)).toEqual([{ name: 'ok', userId: 7 }])
    areas.localStorage.setItem(ACCOUNTS_KEY, 'not json')
    expect(readCreated(store)).toEqual([])
  })
})

describe('validateName', () => {
  it('accepts 1 to 40 characters after trimming', () => {
    expect(validateName('  Minh ')).toEqual({ ok: true, name: 'Minh' })
    expect(validateName('x'.repeat(40)).ok).toBe(true)
  })

  it('rejects empty, blank and too long names with the message of the old page', () => {
    for (const bad of ['', '   ', 'x'.repeat(41)]) {
      const r = validateName(bad)
      expect(r.ok).toBe(false)
      if (!r.ok) expect(r.message).toBe('Vui lòng nhập tên từ 1 đến 40 ký tự.')
    }
  })
})

describe('pickFreshUserId', () => {
  it('returns an id in 500000..599998 whose history is empty', async () => {
    const id = await pickFreshUserId({ hasNoRatings: async () => true, rand: () => 0.5 })
    expect(id).toBe(FRESH_ID_BASE + Math.floor(0.5 * FRESH_ID_SPAN))
    const low = await pickFreshUserId({ hasNoRatings: async () => true, rand: () => 0 })
    const high = await pickFreshUserId({ hasNoRatings: async () => true, rand: () => 0.999999 })
    expect(low).toBe(500000)
    expect(high).toBeLessThanOrEqual(599998)
  })

  it('tries again when an id already has ratings, up to 5 times, then gives up', async () => {
    const asked: number[] = []
    let n = 0
    const none = await pickFreshUserId({
      hasNoRatings: async (id) => (asked.push(id), false),
      rand: () => (n++ % 10) / 10,
    })
    expect(none).toBeNull()
    expect(asked).toHaveLength(5)
  })

  it('stops at the first free id', async () => {
    const asked: number[] = []
    const id = await pickFreshUserId({ hasNoRatings: async (u) => (asked.push(u), asked.length === 3), rand: Math.random })
    expect(asked).toHaveLength(3)
    expect(id).toBe(asked[2])
  })
})
