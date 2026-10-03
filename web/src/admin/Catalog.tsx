import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useId, useState } from 'react'
import { ApiError, type MovieSort } from '@/shared/api/client'
import { useMovies } from '@/shared/hooks/queries'
import { GENRE_NAMES } from '@/shared/lib/genre'
import { cn } from '@/shared/lib/utils'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'
import { Skeleton } from '@/shared/ui/skeleton'
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from '@/shared/ui/table'

const PAGE_SIZE = 20
const SEARCH_DELAY_MS = 300

const SORTS: Array<{ value: MovieSort; label: string; needsStats?: boolean }> = [
  { value: 'ratings', label: 'Số rating' },
  { value: 'avg', label: 'Điểm trung bình', needsStats: true },
  { value: 'wr', label: 'WR', needsStats: true },
  { value: 'title', label: 'Tên phim' },
]

const number = (n: number) => n.toLocaleString('en-US')
const effectiveOrder = (sort: MovieSort, order: 'asc' | 'desc' | null) => order ?? (sort === 'title' ? 'asc' : 'desc')

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(timer)
  }, [value, ms])
  return debounced
}

const SELECT = 'h-11 w-full rounded-md border border-input bg-card px-3 text-sm sm:h-10'

/** The movie catalog (specs/catalog-ui "Admin movie catalog table"): every MovieLens movie and the demo movies, searched by title, filtered by
 *  genre, sorted by rating count, average or WR. The average and WR are the training-split numbers plus the ratings applied since (the same
 *  as the popular list); a movie without one shows a dash. */
export function Catalog() {
  const searchId = useId()
  const genreId = useId()
  const sortId = useId()
  const [text, setText] = useState('')
  const [genre, setGenre] = useState('')
  const [sort, setSort] = useState<MovieSort>('ratings')
  const [order, setOrder] = useState<'asc' | 'desc' | null>(null)
  const [page, setPage] = useState(1)
  const q = useDebounced(text.trim(), SEARCH_DELAY_MS)

  // A new search, filter or sort starts at page 1. Done while rendering, not in an effect: an effect would run after the query had already
  // been sent for the new filter with the old page number.
  const filterKey = `${q}\u0000${genre}\u0000${sort}\u0000${order ?? ''}`
  const [seenKey, setSeenKey] = useState(filterKey)
  if (seenKey !== filterKey) {
    setSeenKey(filterKey)
    setPage(1)
  }

  const query = useMovies({ q, genre: genre || null, sort, order, page, size: PAGE_SIZE })
  const data = query.data
  const direction = effectiveOrder(sort, order)
  const needsStats = sort === 'avg' || sort === 'wr'
  // The server answers 422 for avg / wr when the statistics are not loaded (and the table may still show a page from before they went away).
  const statsGone = query.error instanceof ApiError && query.error.status === 422 && needsStats
  const noStats = (data != null && !data.hasStats) || statsGone

  // Fall back to the rating count instead of leaving the table on an error.
  useEffect(() => {
    if (noStats && needsStats) setSort('ratings')
  }, [noStats, needsStats])

  const DirectionIcon = direction === 'desc' ? ArrowDown : ArrowUp

  return (
    <section aria-labelledby="catalog-title" className="space-y-3 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="catalog-title" className="text-lg font-semibold">
          Danh mục phim
        </h2>
        {data && (
          <p className="text-sm text-muted-foreground" aria-live="polite">
            {number(data.total)} phim{data.pages > 0 ? ` · trang ${page}/${number(data.pages)}` : ''}
          </p>
        )}
      </div>
      <p className="text-sm text-muted-foreground">
        Toàn bộ phim MovieLens và phim demo. Điểm trung bình và WR tính trên tập train cộng các rating đã áp dụng (cùng nguồn với danh sách phổ biến), nên phim ra sau
        10/2016 có số rating nhưng chưa có điểm.
      </p>

      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1 basis-60 space-y-1.5">
          <Label htmlFor={searchId}>Tìm theo tên</Label>
          <Input
            id={searchId}
            type="search"
            value={text}
            maxLength={100}
            placeholder="Ví dụ: pulp, godfather part, 1994"
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        <div className="w-44 space-y-1.5">
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
        <div className="w-48 space-y-1.5">
          <Label htmlFor={sortId}>Sắp xếp theo</Label>
          <select id={sortId} className={SELECT} value={sort} onChange={(e) => setSort(e.target.value as MovieSort)}>
            {SORTS.map((s) => (
              <option key={s.value} value={s.value} disabled={Boolean(s.needsStats && noStats)}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={() => setOrder(direction === 'desc' ? 'asc' : 'desc')}
          aria-label={`Thứ tự: ${direction === 'desc' ? 'giảm dần' : 'tăng dần'}. Bấm để đảo`}
        >
          <DirectionIcon aria-hidden="true" />
          {direction === 'desc' ? 'Giảm dần' : 'Tăng dần'}
        </Button>
      </div>

      {query.isError && !statsGone && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-destructive">
          Không tải được danh mục phim.
          {data && <span className="text-sm">Bảng bên dưới là lần tải trước, số liệu có thể đã cũ.</span>}
          <Button type="button" variant="outline" onClick={() => void query.refetch()}>
            Thử lại
          </Button>
        </div>
      )}

      <div className={cn('rounded-lg border', query.isPlaceholderData && 'opacity-70')} aria-busy={query.isPending || query.isPlaceholderData}>
        {query.isPending ? (
          <div className="space-y-2 p-3">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : data && data.items.length === 0 ? (
          <p className="p-4 text-muted-foreground">Không có phim nào khớp.</p>
        ) : data ? (
          <div className="overflow-x-auto">
            <Table>
              <TableCaption className="sr-only">
                Danh mục phim, {data.total} kết quả, sắp theo {SORTS.find((s) => s.value === sort)?.label}
              </TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">Phim</TableHead>
                  <TableHead scope="col" className="text-right">Số rating</TableHead>
                  <TableHead scope="col" className="text-right">Điểm TB</TableHead>
                  <TableHead scope="col" className="text-right">WR</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((movie) => (
                  <TableRow key={movie.movieId}>
                    <TableCell className="whitespace-normal">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{movie.title}</span>
                        {movie.isDemo && (
                          <span className="rounded border border-warning-text/50 px-1.5 py-0.5 text-[11px] font-semibold uppercase text-warning-text">demo</span>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        <span className="font-mono">#{movie.movieId}</span>
                        {movie.genres.length > 0 ? ` · ${movie.genres.join(' · ')}` : ''}
                      </div>
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {number(movie.ratings)}
                      {movie.newRatings > 0 && <span className="ml-1 text-xs font-semibold text-primary">+{number(movie.newRatings)} mới</span>}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {movie.avgRating == null ? (
                        <span title="Chưa có số liệu: phim không có rating trong tập train" aria-label="chưa có số liệu">
                          —
                        </span>
                      ) : (
                        movie.avgRating.toFixed(3)
                      )}
                    </TableCell>
                    <TableCell className="text-right font-mono font-semibold tabular-nums">
                      {movie.wr == null ? (
                        <span title="Chưa có số liệu: phim không có rating trong tập train" aria-label="chưa có số liệu">
                          —
                        </span>
                      ) : (
                        movie.wr.toFixed(4)
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : null}
      </div>

      {data && data.pages > 1 && (
        <nav aria-label="Phân trang danh mục phim" className="flex flex-wrap items-center justify-between gap-2">
          <Button type="button" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
            <ChevronLeft aria-hidden="true" />
            Trước
          </Button>
          <span className="text-sm text-muted-foreground">
            Trang {page} / {number(data.pages)}
          </span>
          <Button type="button" variant="outline" disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)}>
            Sau
            <ChevronRight aria-hidden="true" />
          </Button>
        </nav>
      )}
    </section>
  )
}
