import { ArrowDown, ArrowUp, Equal, RotateCcw } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import type { PopularityItem } from '@/shared/api/types'
import { usePopularity } from '@/shared/hooks/queries'
import { cn } from '@/shared/lib/utils'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'
import { Skeleton } from '@/shared/ui/skeleton'
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from '@/shared/ui/table'
import { formulaSteps, moveText, parseM, rankMap, rankMoves, trustText, versusBaseline } from './popularityLogic'

const POLL_MS = 3000        // the table refreshes this often while the section is open and the tab is visible
const MARK_MS = 10_000      // a movement marker stays this long
const PREVIEW_DEBOUNCE_MS = 400

const number = (n: number) => n.toLocaleString('en-US')
const clock = (iso: string) => {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleTimeString('en-GB', { hour12: false })
}
const cutoffDate = (epoch: number) => new Date(epoch * 1000).toISOString().slice(0, 10)

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(timer)
  }, [value, ms])
  return debounced
}

/** A movement shown as an arrow AND words, so it does not depend on colour. */
function Move({ delta }: { delta: number }) {
  const up = delta > 0
  const Icon = up ? ArrowUp : ArrowDown
  return (
    <span className={cn('inline-flex items-center gap-1 text-xs font-semibold', up ? 'text-success' : 'text-warning-text')}>
      <Icon className="size-3.5" aria-hidden="true" />
      {moveText(delta)}
    </span>
  )
}

function Baseline({ item }: { item: PopularityItem }) {
  const { delta, text } = versusBaseline(item)
  if (delta === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-muted-foreground">
        <Equal className="size-3.5" aria-hidden="true" />
        {text}
      </span>
    )
  }
  if (delta === null) return <span className="text-muted-foreground">{text}</span>
  const Icon = delta > 0 ? ArrowUp : ArrowDown
  return (
    <span className={cn('inline-flex items-center gap-1 font-medium', delta > 0 ? 'text-success' : 'text-warning-text')}>
      <Icon className="size-3.5" aria-hidden="true" />
      {text}
    </span>
  )
}

function Formula({ item, m, c }: { item: PopularityItem; m: number; c: number | null }) {
  const steps = c == null ? null : formulaSteps(item, m, c)
  if (!steps) {
    return (
      <p className="text-sm text-muted-foreground">
        Danh sách này lấy từ artifact của Quyên nên chỉ có WR ({item.wr.toFixed(3)}) và số rating ({number(item.support)}), không có điểm trung bình để thay vào công thức.
      </p>
    )
  }
  const share = (steps.w * 100).toFixed(1)
  return (
    <div className="space-y-3 text-sm">
      <p className="font-mono">WR = v/(v+m)·R + m/(v+m)·C</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
        <dt className="font-mono text-muted-foreground">v</dt>
        <dd>
          {number(steps.v)} rating ({number(item.baseSupport)} gốc + {number(item.newRatings)} mới)
        </dd>
        <dt className="font-mono text-muted-foreground">R</dt>
        <dd>{steps.r.toFixed(4)} (điểm trung bình của phim)</dd>
        <dt className="font-mono text-muted-foreground">C</dt>
        <dd>{steps.c.toFixed(4)} (điểm trung bình của cả tập train)</dd>
        <dt className="font-mono text-muted-foreground">m</dt>
        <dd>{steps.m} (số rating "tin sẵn" ở mức trung bình chung)</dd>
        <dt className="font-mono text-muted-foreground">w</dt>
        <dd>
          v/(v+m) = {number(steps.v)}/({number(steps.v)}+{steps.m}) = {share}%
        </dd>
        <dt className="font-mono text-muted-foreground">WR</dt>
        <dd>
          {steps.w.toFixed(4)} × {steps.r.toFixed(4)} + {(1 - steps.w).toFixed(4)} × {steps.c.toFixed(4)} ={' '}
          <strong data-testid="formula-wr">{steps.wr.toFixed(4)}</strong>
        </dd>
      </dl>
      <p>{trustText(steps.w)}</p>
    </div>
  )
}

/** The popular list a brand-new user receives, with the numbers behind it (specs/demo-popularity-live). It refreshes by itself
 *  every 3 seconds while the section is open, marks rank changes, and explains one movie's WR step by step. */
export function Popularity() {
  const mFieldId = useId()
  const mErrorId = useId()
  const [mText, setMText] = useState('')
  const typed = parseM(mText)
  const applied = parseM(useDebounced(mText, PREVIEW_DEBOUNCE_MS))
  const query = usePopularity({ m: applied.value, refetchInterval: POLL_MS })
  const data = query.data

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const selected = data?.items.find((i) => i.movieId === selectedId) ?? null

  // Rank movements between two refreshes, kept for MARK_MS. Reset when another m is shown: the two lists are not comparable.
  const previous = useRef<Map<number, number> | null>(null)
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>())
  const [marks, setMarks] = useState<Map<number, number>>(new Map())

  useEffect(() => {
    previous.current = null
    setMarks(new Map())
    timers.current.forEach(clearTimeout)
    timers.current.clear()
  }, [applied.value])

  useEffect(() => () => timers.current.forEach(clearTimeout), [])

  useEffect(() => {
    if (!data) return
    const before = previous.current
    previous.current = rankMap(data.items)
    if (!before) return
    const moves = rankMoves(before, data.items)
    if (moves.size === 0) return
    setMarks((current) => new Map([...current, ...moves]))
    for (const id of moves.keys()) {
      clearTimeout(timers.current.get(id))
      timers.current.set(
        id,
        setTimeout(() => {
          setMarks((current) => {
            const next = new Map(current)
            next.delete(id)
            return next
          })
          timers.current.delete(id)
        }, MARK_MS),
      )
    }
  }, [data])

  const moved = data ? data.items.filter((i) => marks.has(i.movieId)) : []
  const announcement = moved.map((i) => `${i.title} ${moveText(marks.get(i.movieId)!)}`).join('; ')

  return (
    <div className="space-y-4">
      <section aria-labelledby="pop-info" className="space-y-2 rounded-xl border bg-card p-4">
        <h2 id="pop-info" className="text-lg font-semibold">
          Danh sách phổ biến mà user mới nhận
        </h2>
        {data?.source === 'live' && (
          <p className="text-sm">
            Số liệu gốc: <strong>{number(data.baseline!.ratings)}</strong> rating của tập train (đến {cutoffDate(data.baseline!.cutoff)}) cộng{' '}
            <strong>{number(data.appliedEvents)}</strong> rating mới đã áp dụng. m = {data.m}, C = {data.c!.toFixed(4)}, cần ít nhất {data.minSupport} rating để được xét.
          </p>
        )}
        {data && (
          <p className="text-sm text-muted-foreground">
            {data.liveEnabled
              ? 'Cờ popularity.live đang BẬT: user mới nhận đúng danh sách này.'
              : 'Cờ popularity.live đang TẮT: user mới vẫn nhận danh sách artifact. Bảng này là bản tính sống để so sánh.'}{' '}
            Tính lúc {clock(data.generatedAt)}, tự làm mới mỗi {POLL_MS / 1000} giây.
          </p>
        )}
        {data?.source === 'artifact' && (
          <p role="status" className="rounded-md border border-warning-text/40 bg-highlight/20 px-3 py-2 text-sm text-warning-text">
            Chưa có số liệu sống (movie_stats chưa được nạp hoặc đang lỗi), đang hiện danh sách artifact của Quyên, không có điểm trung bình.
          </p>
        )}
        {data?.preview && (
          <p role="status" className="rounded-md border border-primary/40 bg-primary/10 px-3 py-2 text-sm">
            Đang xem trước với m = {data.m}. Hệ thống vẫn dùng m cấu hình, danh sách user nhận không đổi.
          </p>
        )}

        <div className="flex flex-wrap items-end gap-3 pt-1">
          <div className="space-y-1.5">
            <Label htmlFor={mFieldId}>Xem trước với m khác (không đổi hệ thống)</Label>
            <Input
              id={mFieldId}
              type="number"
              inputMode="decimal"
              min={0}
              max={100000}
              step="any"
              value={mText}
              placeholder="để trống = m của hệ thống"
              aria-invalid={typed.invalid}
              aria-describedby={mErrorId}
              onChange={(e) => setMText(e.target.value)}
              className="w-60 font-mono"
            />
          </div>
          {mText !== '' && (
            <Button type="button" variant="outline" onClick={() => setMText('')}>
              <RotateCcw aria-hidden="true" />
              Đặt lại
            </Button>
          )}
          <p id={mErrorId} role="alert" className="basis-full text-sm text-destructive empty:hidden">
            {typed.invalid ? 'Nhập m từ 0 đến 100000.' : ''}
          </p>
        </div>
      </section>

      {query.isError && !data && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-destructive">
          Không tải được danh sách phổ biến.
          <Button type="button" variant="outline" onClick={() => void query.refetch()}>
            Thử lại
          </Button>
        </div>
      )}

      <div className="rounded-xl border bg-card" aria-busy={query.isPending}>
        <p role="status" className="sr-only">
          {announcement}
        </p>
        {query.isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : data ? (
          <div className="overflow-x-auto">
            <Table>
              <TableCaption className="sr-only">
                Top {data.items.length} phim phổ biến xếp theo weighted rating, m = {data.m}
              </TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col" className="w-20">Hạng</TableHead>
                  <TableHead scope="col">Phim</TableHead>
                  <TableHead scope="col" className="text-right">Điểm TB (R)</TableHead>
                  <TableHead scope="col" className="text-right">Số rating (v)</TableHead>
                  <TableHead scope="col" className="text-right">WR</TableHead>
                  <TableHead scope="col">So với danh sách gốc</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((item) => {
                  const mark = marks.get(item.movieId)
                  const isSelected = item.movieId === selectedId
                  return (
                    <TableRow
                      key={item.movieId}
                      data-moved={mark !== undefined ? (mark > 0 ? 'up' : 'down') : undefined}
                      className={cn('transition-colors duration-300 motion-reduce:transition-none', mark !== undefined && 'bg-accent', isSelected && 'bg-muted')}
                    >
                      <TableCell className="font-mono">
                        #{item.rank}
                        {mark !== undefined && (
                          <div>
                            <Move delta={mark} />
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="whitespace-normal">
                        <button
                          type="button"
                          aria-pressed={isSelected}
                          onClick={() => setSelectedId(isSelected ? null : item.movieId)}
                          className="min-h-11 text-left font-medium underline-offset-4 hover:underline focus-visible:underline sm:min-h-10"
                        >
                          {item.title}
                        </button>
                        <div className="text-xs text-muted-foreground">{item.genres.split('|').join(' · ')}</div>
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{item.avgRating == null ? '—' : item.avgRating.toFixed(4)}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {number(item.support)}
                        {item.newRatings > 0 && <span className="ml-1 text-xs font-semibold text-primary">+{number(item.newRatings)} mới</span>}
                      </TableCell>
                      <TableCell className="text-right font-mono font-semibold tabular-nums">{item.wr.toFixed(4)}</TableCell>
                      <TableCell className="text-sm">
                        <Baseline item={item} />
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        ) : null}
      </div>

      {data && (
        <section aria-labelledby="pop-formula" className="space-y-3 rounded-xl border bg-card p-4">
          <h2 id="pop-formula" className="text-lg font-semibold">
            Công thức từng bước
          </h2>
          {selected ? (
            <>
              <p className="font-medium">{selected.title}</p>
              <Formula item={selected} m={data.m} c={data.c} />
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Bấm tên một phim trong bảng để xem WR của nó được tính ra sao.</p>
          )}
        </section>
      )}
    </div>
  )
}
