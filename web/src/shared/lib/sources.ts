import type { Recommendation } from '../api/types'

/** Where a recommendation comes from. The API label can join sources with "+" (e.g. "als+content"). */
export type SourceKey = 'new' | 'als' | 'content' | 'popularity'

/** First match wins when a label has several sources (design D-5). */
export const SOURCE_ORDER: SourceKey[] = ['new', 'als', 'content', 'popularity']

/** Titles in user language: no technical terms on the user page. */
export const SOURCE_TITLES: Record<SourceKey, string> = {
  new: 'Mới thêm',
  als: 'Dành riêng cho bạn',
  content: 'Giống phim bạn đã thích',
  popularity: 'Đang được yêu thích',
}

export function sourcesOf(item: Pick<Recommendation, 'source'>): SourceKey[] {
  return item.source.split('+').filter((s): s is SourceKey => (SOURCE_ORDER as string[]).includes(s))
}

export function primarySource(item: Pick<Recommendation, 'source'>): SourceKey {
  const present = sourcesOf(item)
  return SOURCE_ORDER.find((s) => present.includes(s)) ?? 'popularity'
}

export function reasonOf(item: Pick<Recommendation, 'source'>): string {
  return SOURCE_TITLES[primarySource(item)]
}

export function isNew(item: Pick<Recommendation, 'source'>): boolean {
  return sourcesOf(item).includes('new')
}

export interface SourceRow {
  source: SourceKey
  title: string
  items: Recommendation[]
  bestRank: number
}

export type FeedLayout =
  | { kind: 'rows'; rows: SourceRow[] }
  | { kind: 'grid'; title: string; items: Recommendation[] }
  | { kind: 'empty' }

/** At least two sources: one row per source, ordered by the best rank inside each row.
 *  One source: a single grid under that source's title. Every item keeps its original rank. */
export function layoutFeed(items: Recommendation[]): FeedLayout {
  if (items.length === 0) return { kind: 'empty' }
  const by = new Map<SourceKey, Recommendation[]>()
  for (const item of items) {
    const key = primarySource(item)
    by.set(key, [...(by.get(key) ?? []), item])
  }
  if (by.size === 1) {
    const [key, list] = [...by.entries()][0]!
    return { kind: 'grid', title: SOURCE_TITLES[key], items: list }
  }
  const rows = [...by.entries()]
    .map(([source, list]) => ({
      source,
      title: SOURCE_TITLES[source],
      items: list,
      bestRank: Math.min(...list.map((i) => i.rank)),
    }))
    .sort((a, b) => a.bestRank - b.bestRank)
  return { kind: 'rows', rows }
}
