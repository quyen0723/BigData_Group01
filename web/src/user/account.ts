/** Demo accounts (design D-4). There is no authentication: an account is a name attached to a MovieLens user id. */
export interface Account {
  name: string
  userId: number
}

/** Personas are described by taste only, never by age or gender (PRD §3.2). Each is a real, anonymised MovieLens user. */
export const PERSONAS: Array<Account & { taste: string }> = [
  { name: 'An', userId: 700008, taste: 'Mới xem vài phim, thích phim hình sự' },
  { name: 'Bình', userId: 1, taste: 'Khán giả lâu năm, mê chính kịch và tình cảm' },
  { name: 'Chi', userId: 127249, taste: 'Thích phim hài, phiêu lưu và viễn tưởng' },
]

// The keys of the old page, so accounts created there are still listed.
export const SESSION_KEY = 'mlapp.account'
export const ACCOUNTS_KEY = 'mlapp.accounts'

export type Area = 'sessionStorage' | 'localStorage'

/** Browser storage can be blocked or throw; every read and write is guarded and the page works without it. */
export interface SafeStore {
  get(area: Area, key: string): unknown
  set(area: Area, key: string, value: unknown): void
  remove(area: Area, key: string): void
}

export function safeStore(getArea: (area: Area) => Storage = (a) => window[a]): SafeStore {
  return {
    get(area, key) {
      try {
        const raw = getArea(area).getItem(key)
        return raw == null ? null : JSON.parse(raw)
      } catch {
        return null
      }
    },
    set(area, key, value) {
      try {
        getArea(area).setItem(key, JSON.stringify(value))
      } catch {
        /* no storage: the page runs without memory */
      }
    },
    remove(area, key) {
      try {
        getArea(area).removeItem(key)
      } catch {
        /* ignore */
      }
    },
  }
}

const isAccount = (v: unknown): v is Account =>
  typeof v === 'object' &&
  v !== null &&
  typeof (v as Account).name === 'string' &&
  Number.isInteger((v as Account).userId) &&
  (v as Account).userId > 0

export const readSession = (store: SafeStore): Account | null => {
  const v = store.get('sessionStorage', SESSION_KEY)
  return isAccount(v) ? v : null
}
export const saveSession = (store: SafeStore, account: Account) => store.set('sessionStorage', SESSION_KEY, account)
export const clearSession = (store: SafeStore) => store.remove('sessionStorage', SESSION_KEY)

export const readCreated = (store: SafeStore): Account[] => {
  const v = store.get('localStorage', ACCOUNTS_KEY)
  return Array.isArray(v) ? v.filter(isAccount) : []
}
export const addCreated = (store: SafeStore, account: Account): Account[] => {
  const next = [...readCreated(store), account]
  store.set('localStorage', ACCOUNTS_KEY, next)
  return next
}

export const NAME_MIN = 1
export const NAME_MAX = 40

export function validateName(raw: string): { ok: true; name: string } | { ok: false; message: string } {
  const name = raw.trim()
  if (name.length < NAME_MIN || name.length > NAME_MAX) {
    return { ok: false, message: `Vui lòng nhập tên từ ${NAME_MIN} đến ${NAME_MAX} ký tự.` }
  }
  return { ok: true, name }
}

export const FRESH_ID_BASE = 500000
export const FRESH_ID_SPAN = 99999

/** A user id in 500000..599998 that has rated nothing yet (at most `tries` attempts), or null. */
export async function pickFreshUserId(deps: {
  hasNoRatings: (userId: number) => Promise<boolean>
  rand?: () => number
  tries?: number
}): Promise<number | null> {
  const rand = deps.rand ?? Math.random
  for (let i = 0; i < (deps.tries ?? 5); i++) {
    const id = FRESH_ID_BASE + Math.floor(rand() * FRESH_ID_SPAN)
    if (await deps.hasNoRatings(id)) return id
  }
  return null
}
