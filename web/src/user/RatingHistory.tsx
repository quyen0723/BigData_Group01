import { Star } from 'lucide-react'
import type { RatingHistory as RatingHistoryData } from '@/shared/api/types'
import { splitGenres, splitYear } from '@/shared/lib/movie'

/** "Phim bạn đã đánh giá": the last movies the user rated (50 at most), with the total in the title. */
export function RatingHistory({ data }: { data?: RatingHistoryData }) {
  const total = data?.total ?? 0
  return (
    <section aria-labelledby="historyTitle" className="space-y-3">
      <h2 id="historyTitle" className="text-xl font-semibold">
        Phim bạn đã đánh giá{total ? ` (${total})` : ''}
      </h2>
      {data && total === 0 && (
        <p className="text-muted-foreground">Chưa có phim nào. Hãy chấm sao một vài phim ở trên.</p>
      )}
      {data && total > 0 && (
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {data.items.map((it) => {
            const { title } = splitYear(it.title)
            return (
              <li key={it.movieId} className="flex min-w-0 items-center justify-between gap-3 rounded-lg border bg-card px-3 py-2.5">
                <div className="min-w-0">
                  {it.inCatalog ? (
                    <>
                      <div className="break-words">{title}</div>
                      <div className="text-sm text-muted-foreground">{splitGenres(it.genres).join(' · ')}</div>
                    </>
                  ) : (
                    <div className="italic text-muted-foreground">Phim đã được gỡ khỏi danh mục</div>
                  )}
                </div>
                <span
                  className="inline-flex shrink-0 items-center gap-1 font-mono font-medium text-warning-text"
                  aria-label={it.rating == null ? 'chưa có số sao' : `${it.rating} sao`}
                >
                  <Star className="size-4 fill-current" aria-hidden="true" />
                  <span>{it.rating == null ? '—' : String(it.rating)}</span>
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
