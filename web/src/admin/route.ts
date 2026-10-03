import { useSyncExternalStore } from 'react'

/** The admin sections and their URL hashes (design D-7): reloading or sharing the link opens the same section. */
export const SECTIONS = ['overview', 'cases', 'users', 'movies', 'popularity', 'models', 'log'] as const
export type Section = (typeof SECTIONS)[number]

export interface Route {
  section: Section
  /** Only for `#/users/<id>`. */
  userId: number | null
}

export const SECTION_TITLES: Record<Section, string> = {
  overview: 'Tổng quan',
  cases: 'Case test',
  users: 'Người dùng',
  movies: 'Phim',
  popularity: 'Phổ biến',
  models: 'Model',
  log: 'Nhật ký',
}

/** `#/users/591751` -> users + 591751. An empty or unknown hash opens the overview. */
export function parseHash(hash: string): Route {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  const section = parts[0] as Section | undefined
  if (!section || !SECTIONS.includes(section)) return { section: 'overview', userId: null }
  if (section === 'users' && parts[1] !== undefined) {
    const id = Number(parts[1])
    return { section, userId: Number.isInteger(id) && id > 0 ? id : null }
  }
  return { section, userId: null }
}

export function hrefFor(section: Section, userId?: number | null): string {
  return section === 'users' && userId ? `#/users/${userId}` : `#/${section}`
}

let cached: { hash: string; route: Route } | null = null
function snapshot(): Route {
  const hash = window.location.hash
  if (!cached || cached.hash !== hash) cached = { hash, route: parseHash(hash) }
  return cached.route
}
function subscribe(listener: () => void) {
  window.addEventListener('hashchange', listener)
  return () => window.removeEventListener('hashchange', listener)
}

export function useRoute(): Route {
  return useSyncExternalStore(subscribe, snapshot)
}

export function navigate(section: Section, userId?: number | null) {
  window.location.hash = hrefFor(section, userId)
}
