import { useQueryClient } from '@tanstack/react-query'
import { Film, LogOut } from 'lucide-react'
import { useCallback, useEffect, useRef } from 'react'
import { toast } from 'sonner'
import { keys } from '@/shared/api/keys'
import {
  DEFAULT_POLL_SECONDS,
  DEFAULT_TIER_THRESHOLD,
  useRatingHistory,
  useRecommendations,
  useSystemStatus,
} from '@/shared/hooks/queries'
import { useRatingFlow } from '@/shared/hooks/useRatingFlow'
import { splitYear } from '@/shared/lib/movie'
import type { RatingEvent } from '@/shared/lib/ratingFlow'
import { Button } from '@/shared/ui/button'
import { useAccount } from './AccountContext'
import { Feed } from './Feed'
import { noticeFor } from './events'
import { RatingHistory } from './RatingHistory'
import { TierBanner } from './TierBanner'

export function Home() {
  const { account, logout, signedInHere } = useAccount()
  const userId = account!.userId
  const qc = useQueryClient()

  const system = useSystemStatus()
  const recs = useRecommendations(userId)
  const history = useRatingHistory(userId, 50)
  const pollSeconds = system.data?.demo.ratingPollTimeoutSeconds ?? DEFAULT_POLL_SECONDS
  const threshold = system.data?.demo.tierThreshold ?? DEFAULT_TIER_THRESHOLD

  const helloRef = useRef<HTMLHeadingElement>(null)
  const recsTitleRef = useRef<HTMLHeadingElement>(null)
  const titles = useRef(new Map<number, string>())
  const rateRef = useRef<(movieId: number, stars: number) => void>(() => {})

  useEffect(() => {
    for (const r of recs.data?.recommendations ?? []) titles.current.set(r.movieId, splitYear(r.title).title)
  }, [recs.data])

  // Focus the greeting after the user chose an account (a screen reader announces who is signed in). Not when a saved
  // session is restored on load: focus would jump past the skip link, which then could not be reached with Tab.
  useEffect(() => {
    if (signedInHere) helloRef.current?.focus()
  }, [userId, signedInHere])

  const onEvent = useCallback(
    (event: RatingEvent) => {
      const notice = noticeFor(event, titles.current.get(event.movieId) ?? 'phim này')
      if (!notice) return
      const options =
        notice.retry && event.type === 'failed'
          ? { action: { label: 'Thử lại', onClick: () => rateRef.current(event.movieId, event.stars) } }
          : undefined
      if (notice.kind === 'success') toast.success(notice.text)
      else if (notice.kind === 'error') toast.error(notice.text, options)
      else toast(notice.text)

      if (notice.refresh) {
        const reloads = [qc.invalidateQueries({ queryKey: keys.ratingHistoryOf(userId) })]
        if (notice.refresh === 'all') reloads.push(qc.invalidateQueries({ queryKey: keys.recommendations(userId) }))
        void Promise.all(reloads).then(() => {
          // The grid was redrawn, so focus that sat inside it is gone: put it back at the section heading.
          if (document.activeElement === document.body) recsTitleRef.current?.focus()
        })
      }
    },
    [qc, userId],
  )

  const { pending, rate } = useRatingFlow(userId, { pollSeconds, onEvent })
  useEffect(() => {
    rateRef.current = (movieId, stars) => void rate(movieId, stars)
  }, [rate])

  const total = history.data?.total
  return (
    <>
      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-2 text-lg font-semibold">
            <Film className="size-5 text-primary" aria-hidden="true" />
            <span>MovieLens</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="font-medium">{account!.name}</span>
            <Button variant="outline" onClick={logout}>
              <LogOut aria-hidden="true" />
              Đăng xuất
            </Button>
          </div>
        </div>
      </header>

      <main id="main" tabIndex={-1} className="mx-auto max-w-6xl space-y-6 px-4 py-8 outline-none">
        <div className="space-y-1">
          <h1 ref={helloRef} tabIndex={-1} className="text-3xl font-semibold leading-tight outline-none">
            Xin chào, {account!.name}
          </h1>
          <p className="text-muted-foreground">
            {total == null ? '' : total === 0 ? 'Bạn chưa đánh giá phim nào.' : `Bạn đã đánh giá ${total} phim.`}
          </p>
        </div>

        {total === 0 && (
          <div className="rounded-xl border border-dashed bg-card p-4">
            <strong>Hãy đánh giá vài phim bạn đã xem.</strong>
            <span className="text-muted-foreground">
              {' '}
              Chấm sao ở bên dưới, chúng tôi sẽ dùng chúng để hiểu gu của bạn và gợi ý sát hơn.
            </span>
          </div>
        )}

        <TierBanner
          tier={recs.data?.tier}
          fallbackReason={recs.data?.fallbackReason}
          rated={total}
          threshold={threshold}
        />

        <Feed
          items={recs.data?.recommendations}
          isPending={recs.isPending}
          isError={recs.isError}
          onRetry={() => void recs.refetch()}
          pending={pending}
          onRate={(movieId, stars) => void rate(movieId, stars)}
          headingRef={recsTitleRef}
        />

        <RatingHistory data={history.data} />
      </main>
    </>
  )
}
