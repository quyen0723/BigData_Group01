import { keepPreviousData, useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { api, unwrap, type MovieSort } from '../api/client'
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

/** The live popular list for the admin "Phổ biến" section. TanStack Query pauses the interval while the browser tab is
 *  hidden and stops it when the section unmounts, so nothing is requested in the background. */
export function usePopularity(options: { m: number | null; refetchInterval?: number | false }) {
  return useQuery({
    queryKey: keys.popularity(options.m),
    refetchInterval: options.refetchInterval ?? false,
    refetchIntervalInBackground: false,
    queryFn: async () => unwrap(await api.popularity({ m: options.m })),
  })
}

/** One page of the movie catalog. The previous page stays on screen while the next one loads (no flicker when paging or typing). */
export function useMovies(
  params: { q?: string; genre?: string | null; sort?: MovieSort; order?: 'asc' | 'desc' | null; page?: number; size?: number },
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: keys.movies(params),
    enabled: options.enabled ?? true,
    placeholderData: keepPreviousData,
    queryFn: async () => unwrap(await api.movies(params)),
  })
}

export const SEARCH_PAGE_SIZE = 12

/** The user page's movie search: 12 results at a time, "Xem thêm" loads the next page. Only runs when `enabled`. */
export function useMovieSearch(params: { q: string; genre: string | null }, options: { enabled: boolean }) {
  return useInfiniteQuery({
    queryKey: ['movies', 'search', params] as const,
    enabled: options.enabled,
    initialPageParam: 1,
    queryFn: async ({ pageParam }) => unwrap(await api.movies({ q: params.q, genre: params.genre, page: pageParam, size: SEARCH_PAGE_SIZE })),
    getNextPageParam: (last) => (last.page < last.pages ? last.page + 1 : undefined),
  })
}

export const DEFAULT_POLL_SECONDS = 60
export const DEFAULT_TIER_THRESHOLD = 10
