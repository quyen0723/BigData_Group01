/** TanStack Query keys, in one place so every mutation invalidates the same things. */
export const keys = {
  recommendations: (userId: number) => ['recommendations', userId] as const,
  /** The limit is part of the key: the chooser asks for 1 row (just the total), the home page for 50. Invalidate with
   *  `keys.ratingHistoryOf(userId)` to reload both. */
  ratingHistory: (userId: number, limit: number) => ['ratingHistory', userId, limit] as const,
  ratingHistoryOf: (userId: number) => ['ratingHistory', userId] as const,
  debugUser: (userId: number) => ['debugUser', userId] as const,
  /** The admin page's recommendations: the list plus how long the call took. */
  adminRecs: (userId: number) => ['adminRecs', userId] as const,
  health: ['health'] as const,
  /** One page of the movie catalog for a given search. */
  movies: (params: object) => ['movies', params] as const,
  /** The popular list with its numbers; `m` null = the configured value. */
  popularity: (m: number | null) => ['popularity', m] as const,
  system: ['system'] as const,
  ratingStatus: (eventId: string) => ['ratingStatus', eventId] as const,
}
