import { useEffect, useRef, useState } from 'react'
import { Skeleton } from '@/shared/ui/skeleton'
import { MovieCard } from '@/shared/ui/movie-card'
import { cn } from '@/shared/lib/utils'
import type { UserSession } from './useUserSession'

function Row({ label, value, warn = false, flash = false }: { label: string; value: string; warn?: boolean; flash?: boolean }) {
  return (
    <div className={cn('flex justify-between gap-3 border-b py-1.5 text-sm', warn && 'text-warning-text')}>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={cn('break-words text-right font-mono transition-colors', warn && 'font-semibold', flash && 'font-semibold text-success')}>{value}</dd>
    </div>
  )
}

/** "Quan sát: tier=… · strategy=… · fallbackReason=… · interaction_count=… · user …" under the case card. */
export function observedText(session: UserSession): string {
  const rec = session.recs.data?.rec
  if (!rec) return 'Quan sát: —'
  const count = session.debug.data ? session.debug.data.interaction_count : '?'
  return (
    `Quan sát: tier=${rec.tier} · strategy=${rec.strategy}` +
    (rec.fallbackReason ? ` · fallbackReason=${rec.fallbackReason}` : '') +
    ` · interaction_count=${count} · user ${rec.userId}`
  )
}

/** "Bên trong hệ thống": what the API decided and what is stored for this user. */
export function InternalPanel({ session }: { session: UserSession }) {
  const rec = session.recs.data?.rec
  const latency = session.recs.data?.latencyMs
  const dbg = session.debug.data

  // The tier value is marked for a moment when it changes, so the presenter sees the switch happen.
  const tier = rec?.tier
  const previousTier = useRef<string | undefined>(undefined)
  const [tierChanged, setTierChanged] = useState(false)
  useEffect(() => {
    const before = previousTier.current
    previousTier.current = tier
    if (before && tier && before !== tier) {
      setTierChanged(true)
      const timer = setTimeout(() => setTierChanged(false), 1200)
      return () => clearTimeout(timer)
    }
  }, [tier])

  const batch =
    dbg == null
      ? '—'
      : dbg.pipeline.lastBatchId != null
        ? `#${dbg.pipeline.lastBatchId} @ ${dbg.pipeline.lastRunAt ?? '?'}`
        : '(streaming chưa chạy batch nào)'
  return (
    <section aria-labelledby="internal-title" className="rounded-xl border bg-card p-4">
      <h2 id="internal-title" className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Bên trong hệ thống
      </h2>
      <dl>
        <Row label="user đang xem" value={rec ? String(rec.userId) : '—'} />
        <Row label="tier" value={rec?.tier ?? '—'} flash={tierChanged} />
        <Row label="strategy" value={rec?.strategy ?? '—'} />
        {rec?.fallbackReason && <Row label="fallbackReason" value={rec.fallbackReason} warn />}
        <Row label="modelVersion" value={rec?.modelVersion ?? '—'} />
        <Row label="latency" value={latency != null ? `${latency.toFixed(0)} ms` : '—'} />
        <Row label="interaction_count" value={dbg ? String(dbg.interaction_count) : '—'} />
        <Row label="recent_movieIds" value={dbg ? (dbg.recent_movieIds.slice(0, 5).join(', ') || '—') : '—'} />
        <Row label="positive_movieIds" value={dbg ? (dbg.positive_movieIds.slice(0, 5).join(', ') || '—') : '—'} />
        <Row label="last batch (streaming)" value={batch} />
      </dl>
    </section>
  )
}

/** The recommendations of one user with star rating, next to the internal panel. */
export function UserView({ session }: { session: UserSession }) {
  const { recs } = session
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
      <section aria-labelledby="rec-title" aria-busy={recs.isPending} className="space-y-3">
        <h2 id="rec-title" className="text-lg font-semibold">
          Gợi ý phim
        </h2>
        {recs.isPending && (
          <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-72 rounded-xl" />
            ))}
          </div>
        )}
        {recs.isError && (
          <p role="alert" className="text-destructive">
            Không tải được gợi ý cho user này ({recs.error instanceof Error ? recs.error.message : 'lỗi'}).
          </p>
        )}
        {recs.data && recs.data.rec.recommendations.length === 0 && <p className="text-muted-foreground">Không có gợi ý nào.</p>}
        {recs.data && recs.data.rec.recommendations.length > 0 && (
          <ul className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
            {recs.data.rec.recommendations.map((item) => (
              <li key={item.movieId} className="flex">
                <MovieCard
                  item={item}
                  technical
                  className="w-full"
                  pending={session.pending.get(item.movieId)}
                  onRate={(stars) => session.rate(item.movieId, stars)}
                />
              </li>
            ))}
          </ul>
        )}
      </section>
      <div className="xl:sticky xl:top-4 xl:self-start">
        <InternalPanel session={session} />
      </div>
    </div>
  )
}
