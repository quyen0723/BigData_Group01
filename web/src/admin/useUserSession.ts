import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef } from 'react'
import { api, unwrap } from '@/shared/api/client'
import { keys } from '@/shared/api/keys'
import { DEFAULT_POLL_SECONDS, useDebugUser, useSystemStatus } from '@/shared/hooks/queries'
import { useRatingFlow } from '@/shared/hooks/useRatingFlow'
import type { RatingEvent } from '@/shared/lib/ratingFlow'
import { diffRecs, type Snapshot } from './diff'
import { eventLog } from './eventLog'

/** The recommendation list of one user plus how long the call took (shown in "Bên trong hệ thống"). */
export function useAdminRecs(userId: number | null) {
  return useQuery({
    queryKey: keys.adminRecs(userId ?? 0),
    enabled: userId != null,
    queryFn: async () => {
      const t0 = performance.now()
      const res = await api.recommendations(userId!)
      return { rec: unwrap(res), latencyMs: performance.now() - t0 }
    },
  })
}

function logRatingEvent(userId: number, e: RatingEvent) {
  switch (e.type) {
    case 'sending':
      eventLog.add(`★ rate userId=${userId} movieId=${e.movieId} rating=${e.stars}.0 (eventId=${e.eventId})`)
      break
    case 'accepted':
      eventLog.add(`→ Kafka ✓ (202, eventId=${e.eventId})`, 'ok')
      break
    case 'failed':
      eventLog.add(`✗ POST /ratings -> ${e.status} ${e.detail}`.trim(), 'err')
      break
    case 'applied':
      eventLog.add(`✓ applied (eventId=${e.eventId}, batchId=${e.batchId})`, 'ok')
      break
    case 'timeout':
      eventLog.add(`Hết thời gian: sau ${e.seconds}s vẫn pending (eventId=${e.eventId}) — Streaming pipeline có đang chạy không?`, 'err')
      break
  }
}

/**
 * Everything the admin needs for one user: recommendations, stored state, ratings in flight, and the event log.
 * After a rating is applied, or `requestDiff()` is called (a demo movie was added or removed), the next list is compared
 * with the previous one and the differences are written to the log (design D-7, same messages as the old page).
 */
export function useUserSession(userId: number | null) {
  const qc = useQueryClient()
  const system = useSystemStatus()
  const pollSeconds = system.data?.demo.ratingPollTimeoutSeconds ?? DEFAULT_POLL_SECONDS
  const recs = useAdminRecs(userId)
  const debug = useDebugUser(userId)

  const previous = useRef<Snapshot | null>(null)
  const wantDiff = useRef(false)
  const rated = useRef(new Set<number>())
  const uid = useRef(userId)

  useEffect(() => {
    uid.current = userId
    previous.current = null
    wantDiff.current = false
    rated.current = new Set()
  }, [userId])

  useEffect(() => {
    const rec = recs.data?.rec
    if (!rec) return
    if (wantDiff.current && previous.current) {
      for (const line of diffRecs(previous.current, rec, rated.current)) eventLog.add(line.text, line.kind)
    }
    wantDiff.current = false
    previous.current = { tier: rec.tier, movieIds: rec.recommendations.map((r) => r.movieId) }
  }, [recs.data])

  const reload = useCallback(
    (id: number) =>
      Promise.all([
        qc.invalidateQueries({ queryKey: keys.adminRecs(id) }),
        qc.invalidateQueries({ queryKey: keys.debugUser(id) }),
        qc.invalidateQueries({ queryKey: keys.system }),
      ]),
    [qc],
  )

  const onEvent = useCallback(
    (e: RatingEvent) => {
      const id = uid.current
      if (id == null) return
      if (e.type === 'sending') rated.current.add(e.movieId)
      logRatingEvent(id, e)
      if (e.type === 'applied') {
        wantDiff.current = true
        void reload(id)
      }
    },
    [reload],
  )

  const { pending, rate } = useRatingFlow(userId, { pollSeconds, onEvent })

  return {
    userId,
    recs,
    debug,
    pending,
    rate: (movieId: number, stars: number) => void rate(movieId, stars),
    /** Call before reloading the list after a demo movie was added or removed, so the log shows what changed. */
    requestDiff: () => {
      wantDiff.current = true
    },
    reload: () => (userId == null ? Promise.resolve([]) : reload(userId)),
  }
}

export type UserSession = ReturnType<typeof useUserSession>
