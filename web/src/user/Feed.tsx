import type { Ref } from 'react'
import type { Recommendation } from '@/shared/api/types'
import { layoutFeed } from '@/shared/lib/sources'
import type { PendingRating } from '@/shared/lib/ratingFlow'
import { Button } from '@/shared/ui/button'
import { MovieCard, MovieCardSkeleton } from '@/shared/ui/movie-card'

const GRID = 'grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'   // cards stay wide enough for five 40 px stars on one line

function CardList({
  items,
  pending,
  onRate,
  showReason,
}: {
  items: Recommendation[]
  pending: ReadonlyMap<number, PendingRating>
  onRate: (movieId: number, stars: number) => void
  showReason: boolean
}) {
  return (
    <ul className={GRID}>
      {items.map((item) => (
        <li key={item.movieId} className="flex">
          <MovieCard
            item={item}
            pending={pending.get(item.movieId)}
            showReason={showReason}
            onRate={(stars) => onRate(item.movieId, stars)}
            className="w-full"
          />
        </li>
      ))}
    </ul>
  )
}

/** "Dành cho bạn": a skeleton while loading, an error with a retry, otherwise one row per source (two or more sources)
 *  or a single grid (one source). Every card keeps the rank the system gave it. */
export function Feed({
  items,
  isPending,
  isError,
  onRetry,
  pending,
  onRate,
  headingRef,
}: {
  items?: Recommendation[]
  isPending: boolean
  isError: boolean
  onRetry: () => void
  pending: ReadonlyMap<number, PendingRating>
  onRate: (movieId: number, stars: number) => void
  headingRef?: Ref<HTMLHeadingElement>
}) {
  const layout = items ? layoutFeed(items) : null
  return (
    <section aria-labelledby="recsTitle" aria-busy={isPending} className="space-y-4">
      <h2 id="recsTitle" tabIndex={-1} ref={headingRef} className="text-xl font-semibold outline-none">
        Dành cho bạn
      </h2>

      {isPending && (
        <ul className={GRID} aria-label="Đang tải gợi ý">
          {Array.from({ length: 10 }, (_, i) => (
            <li key={i} className="flex">
              <MovieCardSkeleton />
            </li>
          ))}
        </ul>
      )}

      {isError && !isPending && (
        <p className="text-muted-foreground" role="alert">
          Chưa tải được gợi ý.{' '}
          <Button variant="outline" size="sm" onClick={onRetry}>
            Thử lại
          </Button>
        </p>
      )}

      {layout?.kind === 'empty' && <p className="text-muted-foreground">Hiện chưa có gợi ý nào cho bạn.</p>}

      {layout?.kind === 'grid' && (
        <div className="space-y-3">
          <h3 className="text-base font-semibold text-muted-foreground">{layout.title}</h3>
          <CardList items={layout.items} pending={pending} onRate={onRate} showReason={false} />
        </div>
      )}

      {layout?.kind === 'rows' &&
        layout.rows.map((row) => (
          <div key={row.source} className="space-y-3">
            <h3 className="text-base font-semibold text-muted-foreground">{row.title}</h3>
            <CardList items={row.items} pending={pending} onRate={onRate} showReason={false} />
          </div>
        ))}
    </section>
  )
}
