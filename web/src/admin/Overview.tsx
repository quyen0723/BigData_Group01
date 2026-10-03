import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { api } from '@/shared/api/client'
import { keys } from '@/shared/api/keys'
import { useSystemStatus } from '@/shared/hooks/queries'
import { cn } from '@/shared/lib/utils'
import { hrefFor, type Section } from './route'
import { RetrainProgressBar } from './ModelPanel'

function Kpi({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: 'ok' | 'bad' }) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className={cn('mt-1 break-words font-mono text-2xl font-medium', tone === 'ok' && 'text-success', tone === 'bad' && 'text-destructive')}>{value}</div>
      {hint && <div className="mt-1 text-sm text-muted-foreground">{hint}</div>}
    </div>
  )
}

const LINKS: Array<[Section, string]> = [
  ['cases', 'Chạy một case test'],
  ['users', 'Xem một người dùng'],
  ['movies', 'Thêm phim demo'],
  ['models', 'Vòng đời model'],
]

/** At a glance: the model that is serving, the retrain progress, the demo movies and whether the API answers. */
export function Overview() {
  const system = useSystemStatus({ refetchInterval: 10_000 })
  const health = useQuery({
    queryKey: keys.health,
    refetchInterval: 10_000,
    queryFn: async () => {
      const res = await api.health()
      return res.ok && res.body.status === 'ok'
    },
  })
  const s = system.data
  const active = s?.versions.filter((v) => v.status === 'active').length ?? 0
  const rejected = s?.versions.filter((v) => v.status === 'rejected').length ?? 0

  return (
    <div className="space-y-4">
      {system.isError && (
        <p role="alert" className="text-destructive">
          Không tải được trạng thái hệ thống.
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Kpi label="Model đang chạy" value={s?.activeVersion ?? '—'} hint={s ? `${s.versions.length} version: ${active} active, ${rejected} rejected` : undefined} />
        <Kpi
          label="API"
          value={health.data == null ? '—' : health.data ? 'ok' : 'không trả lời'}
          tone={health.data == null ? undefined : health.data ? 'ok' : 'bad'}
          hint="GET /health, kiểm tra mỗi 10 giây"
        />
        <Kpi
          label="Phim demo"
          value={s ? s.demoMovies.length : '—'}
          hint={s ? `movieId từ ${s.demo.demoMovieIdStart.toLocaleString('en-US')} · nhãn "Mới" ${s.demo.newItemsEnabled ? 'bật' : 'tắt'}` : undefined}
        />
        <Kpi label="Ngưỡng tier (T)" value={s?.demo.tierThreshold ?? '—'} hint="Số rating để user rời tier few_history" />
        <Kpi label="Chờ phản hồi rating" value={s ? `${s.demo.ratingPollTimeoutSeconds} s` : '—'} hint="Thời gian tối đa chờ trạng thái applied" />
      </div>

      <section aria-labelledby="ov-retrain" className="space-y-3 rounded-xl border bg-card p-4">
        <h2 id="ov-retrain" className="text-lg font-semibold">
          Tiến độ retrain
        </h2>
        {s ? <RetrainProgressBar progress={s.retrainProgress} /> : <p className="text-muted-foreground">Đang tải…</p>}
      </section>

      <nav aria-label="Lối tắt" className="flex flex-wrap gap-2">
        {LINKS.map(([section, label]) => (
          <a
            key={section}
            href={hrefFor(section)}
            className="inline-flex min-h-11 items-center rounded-md border bg-card px-4 text-sm font-medium transition-colors hover:border-primary hover:bg-accent sm:min-h-10"
          >
            {label}
          </a>
        ))}
      </nav>
    </div>
  )
}
