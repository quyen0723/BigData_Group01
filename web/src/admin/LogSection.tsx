import { Trash2 } from 'lucide-react'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/utils'
import { eventLog, useEventLog, type LogKind } from './eventLog'

const TONE: Record<LogKind, string> = {
  info: 'text-muted-foreground',
  ok: 'text-success',
  err: 'text-destructive',
}

/** The session's event log: newest first, with the time of each line. */
export function LogLines({ limit }: { limit?: number }) {
  const entries = useEventLog()
  const shown = limit ? entries.slice(0, limit) : entries
  if (shown.length === 0) return <p className="text-muted-foreground">Chưa có sự kiện nào. Chọn một case test hoặc chấm sao một phim.</p>
  return (
    <ul role="log" aria-live="polite" aria-label="Nhật ký sự kiện" className="max-h-[32rem] overflow-y-auto font-mono text-xs">
      {shown.map((e) => (
        <li key={e.id} className={cn('border-b py-1.5', TONE[e.kind])}>
          <span className="mr-2 text-muted-foreground">[{e.time}]</span>
          {e.text}
          {e.kind === 'err' && <span className="sr-only"> (lỗi)</span>}
        </li>
      ))}
    </ul>
  )
}

/** The last few lines, shown under the case test and user views so the presenter sees events as they happen. */
export function RecentLog() {
  return (
    <section aria-labelledby="recent-log" className="space-y-2 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="recent-log" className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Nhật ký gần đây
        </h2>
        <a className="text-sm text-primary underline underline-offset-4 hover:text-primary-hover" href="#/log">
          Xem toàn bộ
        </a>
      </div>
      <LogLines limit={8} />
    </section>
  )
}

export function LogSection() {
  const entries = useEventLog()
  return (
    <section aria-labelledby="log-title" className="space-y-3 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="log-title" className="text-lg font-semibold">
          Nhật ký sự kiện
        </h2>
        <Button variant="outline" onClick={() => eventLog.clear()} disabled={entries.length === 0}>
          <Trash2 aria-hidden="true" />
          Xoá nhật ký
        </Button>
      </div>
      <LogLines />
      <p className="text-xs text-muted-foreground">Trang này không tải bất kỳ tài nguyên nào từ internet — chỉ gọi API cùng origin.</p>
    </section>
  )
}
