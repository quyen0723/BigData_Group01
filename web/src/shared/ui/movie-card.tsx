import { Loader2 } from 'lucide-react'
import type { Recommendation } from '../api/types'
import type { PendingRating } from '../lib/ratingFlow'
import { splitGenres, splitYear } from '../lib/movie'
import { isNew, reasonOf } from '../lib/sources'
import { cn } from '../lib/utils'
import { GenreTile } from './genre-tile'
import { StarRating } from './star-rating'

const STATE_TEXT = {
  sending: 'Đang gửi đánh giá…',
  updating: 'Đang cập nhật gợi ý…',
} as const

/**
 * One recommended movie (design D-5). It keeps the rank the system gave it. `pending` is the rating in flight for this
 * movie: the stars stay locked and a status line says what is happening. `technical` is the admin view: raw score and
 * source label instead of the reason in user language.
 */
export function MovieCard({
  item,
  pending,
  onRate,
  showReason = true,
  technical = false,
  className,
}: {
  item: Recommendation
  pending?: PendingRating
  onRate: (stars: number) => void
  showReason?: boolean
  technical?: boolean
  className?: string
}) {
  const { title, year } = splitYear(item.title)
  const genres = splitGenres(item.genres).slice(0, 3)
  return (
    <article
      className={cn(
        'relative flex min-w-0 flex-col overflow-hidden rounded-xl border bg-card text-card-foreground shadow-xs transition-opacity',
        pending && 'opacity-80',
        className,
      )}
      aria-busy={pending ? true : undefined}
    >
      {isNew(item) && (
        <span className="absolute right-2 top-2 z-10 rounded-full bg-highlight px-2.5 py-0.5 text-xs font-semibold text-highlight-foreground">
          Mới
        </span>
      )}
      <GenreTile genres={item.genres} />
      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="font-mono text-xs text-muted-foreground">
          #{item.rank}
          {technical && <> · score {item.score.toFixed(4)}</>}
        </div>
        <h3 className="line-clamp-2 text-base font-semibold leading-snug" title={title}>
          {title}
        </h3>
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          {year != null && <span className="font-mono">{year}</span>}
          {genres.map((g) => (
            <span key={g} className="rounded-full border px-2 py-0.5">
              {g}
            </span>
          ))}
        </div>
        {technical ? (
          <div className="font-mono text-xs uppercase text-muted-foreground">nguồn: {item.source}</div>
        ) : (
          showReason && <div className="text-sm font-medium text-primary">{reasonOf(item)}</div>
        )}
        <div className="mt-auto pt-1">
          <StarRating
            label={`Chấm sao cho ${title}`}
            onRate={onRate}
            disabled={Boolean(pending)}
            chosen={pending?.stars ?? null}
          />
        </div>
        <div className="flex min-h-5 items-center gap-2 text-sm text-muted-foreground" role="status" aria-live="polite">
          {pending && (
            <>
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              <span>{STATE_TEXT[pending.phase]}</span>
            </>
          )}
        </div>
      </div>
    </article>
  )
}

/** A card-shaped placeholder that keeps the final size while the list loads. */
export function MovieCardSkeleton() {
  return (
    <div className="min-h-[19rem] animate-pulse rounded-xl border bg-card" aria-hidden="true">
      <div className="h-24 rounded-t-xl bg-muted" />
      <div className="space-y-3 p-3">
        <div className="h-3 w-10 rounded bg-muted" />
        <div className="h-5 w-3/4 rounded bg-muted" />
        <div className="h-4 w-1/2 rounded bg-muted" />
        <div className="h-8 w-full rounded bg-muted" />
      </div>
    </div>
  )
}
