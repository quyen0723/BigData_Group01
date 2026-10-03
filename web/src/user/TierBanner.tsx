import { Info } from 'lucide-react'
import { bannerFor } from '@/shared/lib/tier'
import { Progress } from '@/shared/ui/progress'

/** Why these movies are shown, in plain words (design D-5). The live region exists from the first render and only its
 *  content changes: a region that appears together with its text is not reliably announced. While data is loading it
 *  keeps its height so the page does not jump. */
export function TierBanner({
  tier,
  fallbackReason,
  rated,
  threshold,
}: {
  tier?: string
  fallbackReason?: string | null
  rated?: number
  threshold: number
}) {
  const loading = tier == null || rated == null
  const banner = loading ? null : bannerFor({ tier, fallbackReason: fallbackReason ?? null, rated, threshold })
  return (
    <section
      aria-label="Vì sao bạn thấy những phim này"
      role="status"
      aria-live="polite"
      aria-busy={loading}
      className={
        loading
          ? 'min-h-24 animate-pulse rounded-xl border bg-card'
          : 'flex gap-3 rounded-xl border border-primary/30 bg-accent p-4 text-accent-foreground'
      }
    >
      {banner && (
        <>
          <Info className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
          <div className="min-w-0 flex-1 space-y-2">
            <p className="font-medium">{banner.text}</p>
            {banner.extra && <p className="text-sm">{banner.extra}</p>}
            {banner.progress && (
              <div className="flex items-center gap-3">
                <Progress
                  value={(banner.progress.value / banner.progress.max) * 100}
                  aria-label={`Đã chấm ${banner.progress.value} trên ${banner.progress.max} phim`}
                  className="h-2.5 max-w-xs bg-primary/20"
                />
                <span className="font-mono text-sm">
                  {banner.progress.value}/{banner.progress.max}
                </span>
              </div>
            )}
          </div>
        </>
      )}
    </section>
  )
}
