import { useEffect, useId, useMemo, useState } from 'react'
import type { MovieRow, Recommendation } from '@/shared/api/types'
import { SEARCH_PAGE_SIZE, useMovieSearch } from '@/shared/hooks/queries'
import { GENRE_NAMES } from '@/shared/lib/genre'
import type { PendingRating } from '@/shared/lib/ratingFlow'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'
import { MovieCard, MovieCardSkeleton } from '@/shared/ui/movie-card'

const MIN_CHARS = 2
const SEARCH_DELAY_MS = 300

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(timer)
  }, [value, ms])
  return debounced
}

/** A catalog row as the card expects a movie: no rank, and not a recommendation. */
const asCardItem = (row: MovieRow): Recommendation => ({
  movieId: row.movieId,
  title: row.title,
  genres: row.genres.join('|'),
  rank: 0,
  score: 0,
  source: 'search',
})

const SELECT = 'h-11 w-full rounded-md border border-input bg-card px-3 text-sm sm:h-10'

/**
 * "Tìm phim để chấm" (specs/catalog-ui "User page movie search"): find any movie by title or genre and rate it with the page's own rating flow.
 * Nothing technical is shown (no averages, no WR). A movie the user rated recently says so, and can be rated again.
 */
export function MovieSearch({
  pending,
  onRate,
  ratedStars,
  rememberTitle,
}: {
  pending: ReadonlyMap<number, PendingRating>
  onRate: (movieId: number, stars: number) => void
  ratedStars: ReadonlyMap<number, number>
  /** Tells the page the title of every result shown, so a toast about a rating can name the movie. */
  rememberTitle: (movieId: number, title: string) => void
}) {
  const searchId = useId()
  const genreId = useId()
  const hintId = useId()
  const [text, setText] = useState('')
  const [genre, setGenre] = useState('')
  const q = useDebounced(text.trim(), SEARCH_DELAY_MS)

  const typed = text.trim().length
  const enough = typed >= MIN_CHARS || genre !== ''
  const ready = q.length >= MIN_CHARS || genre !== ''
  const search = useMovieSearch({ q: q.length >= MIN_CHARS ? q : '', genre: genre || null }, { enabled: ready })
  const pages = search.data?.pages
  const items = useMemo(() => pages?.flatMap((p) => p.items) ?? [], [pages])
  const total = pages?.[0]?.total ?? 0
  // With a genre selected one letter is enough to search, but the letter itself is not used: say so, or the box looks broken.
  const nameIgnored = genre !== '' && typed > 0 && typed < MIN_CHARS

  useEffect(() => {
    for (const row of items) rememberTitle(row.movieId, row.title)
  }, [items, rememberTitle])

  return (
    <section aria-labelledby="searchTitle" className="space-y-4">
      <h2 id="searchTitle" className="text-xl font-semibold">
        Tìm phim để chấm
      </h2>

      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1 basis-64 space-y-1.5">
          <Label htmlFor={searchId}>Tên phim</Label>
          <Input
            id={searchId}
            type="search"
            value={text}
            maxLength={100}
            placeholder="Ví dụ: pulp fiction"
            aria-describedby={hintId}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        <div className="w-48 space-y-1.5">
          <Label htmlFor={genreId}>Thể loại</Label>
          <select id={genreId} className={SELECT} value={genre} onChange={(e) => setGenre(e.target.value)}>
            <option value="">Tất cả</option>
            {GENRE_NAMES.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </div>
      </div>

      <p id={hintId} className="min-h-5 text-sm text-muted-foreground" aria-live="polite">
        {!enough
          ? typed > 0
            ? `Nhập ít nhất ${MIN_CHARS} ký tự hoặc chọn một thể loại.`
            : 'Gõ tên phim hoặc chọn một thể loại để tìm. Chấm sao để hệ thống hiểu gu của bạn.'
          : [
              search.isSuccess && items.length > 0
                ? `Tìm thấy ${total.toLocaleString('en-US')} phim${total > items.length ? `, đang hiện ${items.length}` : ''}.`
                : '',
              nameIgnored ? `Tên phim cần ít nhất ${MIN_CHARS} ký tự nên chưa được dùng để lọc.` : '',
            ]
              .filter(Boolean)
              .join(' ')}
      </p>

      {enough && search.isPending && search.fetchStatus !== 'idle' && (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" aria-label="Đang tìm phim">
          {Array.from({ length: 4 }, (_, i) => (
            <li key={i} className="flex">
              <MovieCardSkeleton />
            </li>
          ))}
        </ul>
      )}

      {search.isError && (
        <p className="text-muted-foreground" role="alert">
          Chưa tìm được phim.{' '}
          <Button variant="outline" size="sm" onClick={() => void search.refetch()}>
            Thử lại
          </Button>
        </p>
      )}

      {enough && search.isSuccess && items.length === 0 && (
        <p className="text-muted-foreground">
          Không tìm thấy phim nào.{' '}
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setText('')
              setGenre('')
            }}
          >
            Xoá tìm kiếm
          </Button>
        </p>
      )}

      {items.length > 0 && (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {items.map((row) => (
            <li key={row.movieId} className="flex">
              <MovieCard
                item={asCardItem(row)}
                pending={pending.get(row.movieId)}
                showRank={false}
                showReason={false}
                ratedStars={ratedStars.get(row.movieId) ?? null}
                onRate={(stars) => onRate(row.movieId, stars)}
                className="w-full"
              />
            </li>
          ))}
        </ul>
      )}

      {search.hasNextPage && (
        <div>
          <Button variant="outline" onClick={() => void search.fetchNextPage()} disabled={search.isFetchingNextPage}>
            {search.isFetchingNextPage ? 'Đang tải…' : `Xem thêm (${Math.min(SEARCH_PAGE_SIZE, total - items.length)})`}
          </Button>
        </div>
      )}
    </section>
  )
}
