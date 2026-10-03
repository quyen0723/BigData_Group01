import { api as realApi, detailOf } from '../api/client'
import { isFinalAnswer, type RetryIds } from './retry'

/** What happens to one rating, for toasts (user page) and the event log (admin page). */
export type RatingEvent =
  | { type: 'sending'; movieId: number; stars: number; eventId: string }
  | { type: 'accepted'; movieId: number; stars: number; eventId: string }
  | { type: 'failed'; movieId: number; stars: number; eventId: string; status: number; detail: string }
  | { type: 'applied'; movieId: number; eventId: string; batchId: number | null }
  | { type: 'timeout'; movieId: number; eventId: string; seconds: number }

export type Phase = 'sending' | 'updating'
export interface PendingRating {
  stars: number
  phase: Phase
  eventId: string
}

export interface FlowDeps {
  userId: number
  api?: Pick<typeof realApi, 'postRating' | 'ratingStatus'>
  retry: RetryIds
  /** How long to wait for "applied", read each time (it comes from /debug/system and can change). */
  pollSeconds: () => number
  onEvent: (event: RatingEvent) => void
  pollIntervalMs?: number
}

/**
 * The life of ratings sent from one page (design D-3): POST, then poll `GET /ratings/{eventId}` until it is
 * applied or the wait runs out. It lives outside the cards on purpose: when the feed is refetched a card can move to
 * another row and be mounted again, but the pending state, and so its locked stars, must survive that.
 * Rules carried over from the old pages: at most one rating in flight per movie, the same eventId when the same
 * rating is retried, polling stops when the account changes (dispose).
 */
export class RatingFlow {
  private pending = new Map<number, PendingRating>()
  private snapshot: ReadonlyMap<number, PendingRating> = this.pending
  private listeners = new Set<() => void>()
  private timers = new Set<ReturnType<typeof setTimeout>>()
  private disposed = false
  private readonly api: NonNullable<FlowDeps['api']>

  constructor(private readonly deps: FlowDeps) {
    this.api = deps.api ?? realApi
  }

  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }

  getSnapshot = (): ReadonlyMap<number, PendingRating> => this.snapshot

  isPending(movieId: number) {
    return this.pending.has(movieId)
  }

  async rate(movieId: number, stars: number): Promise<void> {
    if (this.disposed || this.pending.has(movieId)) return
    const { userId, retry } = this.deps
    const eventId = retry.idFor(userId, movieId, stars)
    this.set(movieId, { stars, phase: 'sending', eventId })
    this.deps.onEvent({ type: 'sending', movieId, stars, eventId })

    const res = await this.api.postRating({ userId, movieId, rating: stars, eventId })
    if (this.disposed) return
    if (isFinalAnswer(res.status)) retry.forget(userId, movieId)
    if (res.status !== 202) {
      this.drop(movieId)
      this.deps.onEvent({ type: 'failed', movieId, stars, eventId, status: res.status, detail: detailOf(res) })
      return
    }
    this.set(movieId, { stars, phase: 'updating', eventId })
    this.deps.onEvent({ type: 'accepted', movieId, stars, eventId })
    void this.poll(movieId, eventId, 0)
  }

  dispose() {
    this.disposed = true
    for (const t of this.timers) clearTimeout(t)
    this.timers.clear()
    this.pending = new Map()
    this.snapshot = this.pending
    this.listeners.clear()
  }

  private async poll(movieId: number, eventId: string, attempt: number): Promise<void> {
    if (this.disposed) return
    const seconds = this.deps.pollSeconds()
    if (attempt >= seconds) {
      this.drop(movieId)
      this.deps.onEvent({ type: 'timeout', movieId, eventId, seconds })
      return
    }
    const res = await this.api.ratingStatus(eventId)
    if (this.disposed) return
    if (res.ok && res.body.status === 'applied') {
      this.drop(movieId)
      this.deps.onEvent({ type: 'applied', movieId, eventId, batchId: res.body.batchId ?? null })
      return
    }
    const timer = setTimeout(() => {
      this.timers.delete(timer)
      void this.poll(movieId, eventId, attempt + 1)
    }, this.deps.pollIntervalMs ?? 1000)
    this.timers.add(timer)
  }

  private set(movieId: number, value: PendingRating) {
    this.pending = new Map(this.pending).set(movieId, value)
    this.publish()
  }

  private drop(movieId: number) {
    if (!this.pending.has(movieId)) return
    const next = new Map(this.pending)
    next.delete(movieId)
    this.pending = next
    this.publish()
  }

  private publish() {
    this.snapshot = this.pending
    for (const l of this.listeners) l()
  }
}
