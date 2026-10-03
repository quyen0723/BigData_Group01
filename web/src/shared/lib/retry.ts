/** Event ids kept for retrying a rating (design D-3).
 *
 *  A rating that did not come back as a clear yes or no (network error, 5xx, a 503 timeout) may still have
 *  reached Kafka. Sending the same rating again with the same eventId lets the pipeline collapse the two into one.
 *  A final answer (202 or 422) for a movie drops the ids kept for EVERY star value of that movie: an id left behind
 *  at another value could be reused later and, if the broker had accepted it, the ledger would swallow the new rating. */
export interface RetryIds {
  idFor(userId: number, movieId: number, stars: number): string
  forget(userId: number, movieId: number): void
  clear(): void
  size(): number
}

export function createRetryIds(newId: () => string = () => crypto.randomUUID()): RetryIds {
  const ids = new Map<string, string>()
  const key = (u: number, m: number, s: number) => `${u}:${m}:${s}`
  return {
    idFor(userId, movieId, stars) {
      const k = key(userId, movieId, stars)
      let id = ids.get(k)
      if (!id) {
        id = newId()
        ids.set(k, id)
      }
      return id
    },
    forget(userId, movieId) {
      const prefix = `${userId}:${movieId}:`
      for (const k of [...ids.keys()]) if (k.startsWith(prefix)) ids.delete(k)
    },
    clear() {
      ids.clear()
    },
    size: () => ids.size,
  }
}

/** Statuses that end an attempt: the next rating of this movie is a new one. */
export const isFinalAnswer = (status: number) => status === 202 || status === 422
