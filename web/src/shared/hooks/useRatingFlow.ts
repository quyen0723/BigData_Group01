import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { createRetryIds, type RetryIds } from '../lib/retry'
import { RatingFlow, type PendingRating, type RatingEvent } from '../lib/ratingFlow'

const EMPTY: ReadonlyMap<number, PendingRating> = new Map()
const noop = () => () => {}

/**
 * Ratings sent for one account. A new flow (and a new set of retry ids) is made when the account changes and the old
 * one is disposed, so nothing from another account lingers: polls stop and ids are gone.
 * `pollSeconds` and `onEvent` are read through a ref, so changing them does not restart anything.
 */
export function useRatingFlow(
  userId: number | null,
  options: { pollSeconds: number; onEvent: (event: RatingEvent) => void },
) {
  const latest = useRef(options)
  useEffect(() => {
    latest.current = options
  })

  const [flow, setFlow] = useState<RatingFlow | null>(null)
  const retry = useRef<RetryIds | null>(null)

  useEffect(() => {
    if (userId == null) {
      setFlow(null)
      return
    }
    retry.current = createRetryIds()
    const next = new RatingFlow({
      userId,
      retry: retry.current,
      pollSeconds: () => latest.current.pollSeconds,
      onEvent: (e) => latest.current.onEvent(e),
    })
    setFlow(next)
    return () => {
      next.dispose()
      retry.current?.clear()
    }
  }, [userId])

  const pending = useSyncExternalStore(
    flow ? flow.subscribe : noop,
    flow ? flow.getSnapshot : () => EMPTY,
  )
  const rate = useCallback((movieId: number, stars: number) => flow?.rate(movieId, stars), [flow])
  return { pending, rate }
}
