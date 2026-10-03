import type { PopularityItem } from '@/shared/api/types'

/** The pure side of the "Phổ biến" section (specs/demo-popularity-live "Admin Popularity section"). */

export const M_MIN = 0
export const M_MAX = 100_000

/** The text of the preview field -> a number, or null when it is empty, `invalid` when it is not a valid m. */
export function parseM(text: string): { value: number | null; invalid: boolean } {
  const trimmed = text.trim()
  if (trimmed === '') return { value: null, invalid: false }
  const value = Number(trimmed)
  if (!Number.isFinite(value) || value < M_MIN || value > M_MAX) return { value: null, invalid: true }
  return { value, invalid: false }
}

/** movieId -> rank, for comparing two refreshes. */
export function rankMap(items: readonly PopularityItem[]): Map<number, number> {
  return new Map(items.map((i) => [i.movieId, i.rank]))
}

/** How ranks changed between two refreshes: positive = moved up. A movie that was not in the previous list is not a "move". */
export function rankMoves(previous: ReadonlyMap<number, number>, items: readonly PopularityItem[]): Map<number, number> {
  const moves = new Map<number, number>()
  for (const item of items) {
    const before = previous.get(item.movieId)
    if (before !== undefined && before !== item.rank) moves.set(item.movieId, before - item.rank)
  }
  return moves
}

/** "lên 1" / "xuống 2": the movement as words (an arrow alone would be colour and shape only). */
export function moveText(delta: number): string {
  return delta > 0 ? `lên ${delta}` : `xuống ${-delta}`
}

/** Rank against the baseline (the offline list, before any new rating): the persistent column. */
export function versusBaseline(item: PopularityItem): { delta: number | null; text: string } {
  if (item.baseRank == null) return { delta: null, text: 'ngoài top 200 ở bản gốc' }
  const delta = item.baseRank - item.rank
  if (delta === 0) return { delta: 0, text: `giữ hạng gốc #${item.baseRank}` }
  return { delta, text: `${moveText(delta)} so với gốc #${item.baseRank}` }
}

export interface FormulaSteps {
  v: number
  r: number
  c: number
  m: number
  /** v/(v+m): the share of the movie's own average that is kept. */
  w: number
  wr: number
}

/** The numbers of WR = v/(v+m)·R + m/(v+m)·C for one row; `wr` is computed here from the shown numbers, so a mismatch with the table would show. */
export function formulaSteps(item: PopularityItem, m: number, c: number): FormulaSteps | null {
  if (item.avgRating == null) return null
  const v = item.support
  const w = v + m > 0 ? v / (v + m) : 1
  return { v, r: item.avgRating, c, m, w, wr: w * item.avgRating + (1 - w) * c }
}

/** The weight in words, with whole percentages that add up to 100. */
export function trustText(w: number): string {
  const own = Math.round(w * 100)
  return `Phim này được tin ${own}% điểm riêng của nó, ${100 - own}% bị kéo về điểm trung bình chung.`
}
