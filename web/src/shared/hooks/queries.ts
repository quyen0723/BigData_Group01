import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '../api/client'
import { keys } from '../api/keys'

/** The recommendation list. Refetching in the background (window focus) keeps the old data on screen, so the
 *  feed is redrawn only when something changed. */
export function useRecommendations(userId: number | null, k = 10) {
  return useQuery({
    queryKey: keys.recommendations(userId ?? 0),
    enabled: userId != null,
    queryFn: async () => unwrap(await api.recommendations(userId!, k)),
  })
}

export function useRatingHistory(userId: number | null, limit = 50) {
  return useQuery({
    queryKey: keys.ratingHistory(userId ?? 0, limit),
    enabled: userId != null,
    queryFn: async () => unwrap(await api.ratingHistory(userId!, limit)),
  })
}

export function useDebugUser(userId: number | null) {
  return useQuery({
    queryKey: keys.debugUser(userId ?? 0),
    enabled: userId != null,
    queryFn: async () => unwrap(await api.debugUser(userId!)),
  })
}

/** Model lifecycle, retrain progress, demo movies and the demo settings. `refetchInterval` is set only by the admin
 *  sections that show it live; the user page reads it once for the poll timeout and the tier threshold. */
export function useSystemStatus(options: { refetchInterval?: number | false; enabled?: boolean } = {}) {
  return useQuery({
    queryKey: keys.system,
    enabled: options.enabled ?? true,
    refetchInterval: options.refetchInterval ?? false,
    queryFn: async () => unwrap(await api.system()),
  })
}

export const DEFAULT_POLL_SECONDS = 60
export const DEFAULT_TIER_THRESHOLD = 10
