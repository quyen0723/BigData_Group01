import type { Recommendation } from '@/shared/api/types'

export interface Snapshot {
  tier: string
  movieIds: number[]
}

export interface DiffLine {
  text: string
  kind: 'ok'
}

/**
 * What changed between two recommendation lists, for the event log, after a rating was applied or a demo movie was
 * added or removed (same messages as the old admin page): a tier change, movies that left the list (rated by the
 * presenter, or pushed out by a rank change), and new movies that appeared.
 */
export function diffRecs(prev: Snapshot, next: { tier: string; recommendations: Recommendation[] }, rated: ReadonlySet<number>): DiffLine[] {
  const lines: DiffLine[] = []
  if (prev.tier !== next.tier) lines.push({ kind: 'ok', text: `tier đổi: ${prev.tier} → ${next.tier}` })

  const nextIds = new Set(next.recommendations.map((r) => r.movieId))
  let pushedOut = 0
  for (const id of prev.movieIds) {
    if (nextIds.has(id)) continue
    if (rated.has(id)) lines.push({ kind: 'ok', text: `phim movieId=${id} không còn trong danh sách gợi ý (vừa được rate nên bị loại)` })
    else pushedOut++
  }
  if (pushedOut) lines.push({ kind: 'ok', text: `${pushedOut} phim khác không còn trong top-k (bị đẩy ra do thứ hạng thay đổi)` })

  const before = new Set(prev.movieIds)
  for (const r of next.recommendations) {
    if (r.source.split('+').includes('new') && !before.has(r.movieId)) {
      lines.push({ kind: 'ok', text: `phim MỚI movieId=${r.movieId} (${r.title}) xuất hiện ở hạng ${r.rank}` })
    }
  }
  return lines
}
