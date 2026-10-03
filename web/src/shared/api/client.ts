import type {
  DebugUser,
  MovieCreated,
  MovieList,
  Popularity,
  RatingAccepted,
  RatingHistory,
  RatingStatus,
  RecommendationResponse,
  SystemStatus,
} from './types'

export type MovieSort = 'title' | 'ratings' | 'avg' | 'wr'

/** What every call returns: like the old pages, never throws. A network failure is `status: 0`. */
export interface ApiResult<T> {
  ok: boolean
  status: number
  body: T
}

export async function fetchJson<T>(url: string, init?: RequestInit): Promise<ApiResult<T>> {
  try {
    const resp = await fetch(url, init)
    const body = (await resp.json().catch(() => ({}))) as T
    return { ok: resp.ok, status: resp.status, body }
  } catch {
    return { ok: false, status: 0, body: {} as T }
  }
}

/** The `detail` text of an API error, for logs and toasts. */
export function detailOf(res: ApiResult<unknown>): string {
  const detail = (res.body as { detail?: unknown } | undefined)?.detail
  if (typeof detail === 'string') return detail
  return detail ? JSON.stringify(detail) : ''
}

/** Thrown by `unwrap` so TanStack Query puts a failed call into its error state. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message?: string,
  ) {
    super(message ?? (status === 0 ? 'network error' : `HTTP ${status}`))
  }
}

export function unwrap<T>(res: ApiResult<T>): T {
  if (!res.ok) throw new ApiError(res.status, detailOf(res) || undefined)
  return res.body
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  recommendations: (userId: number, k = 10) =>
    fetchJson<RecommendationResponse>(`/recommendations/${userId}?k=${k}`),

  ratingHistory: (userId: number, limit = 50) =>
    fetchJson<RatingHistory>(`/users/${userId}/ratings?limit=${limit}`),

  debugUser: (userId: number) => fetchJson<DebugUser>(`/debug/users/${userId}`),

  system: () => fetchJson<SystemStatus>('/debug/system'),

  health: () => fetchJson<{ status: string }>('/health'),

  /** The movie catalog, searched (demo-only). `order` empty = the server default for the sort key. */
  movies: (params: { q?: string; genre?: string | null; sort?: MovieSort; order?: 'asc' | 'desc' | null; page?: number; size?: number } = {}) => {
    const query = new URLSearchParams({ page: String(params.page ?? 1), size: String(params.size ?? 20), sort: params.sort ?? 'ratings' })
    if (params.q?.trim()) query.set('q', params.q.trim())
    if (params.genre) query.set('genre', params.genre)
    if (params.order) query.set('order', params.order)
    return fetchJson<MovieList>(`/movies?${query.toString()}`)
  },

  /** The numbers behind the popular list (demo-only). `m` is a what-if: serving keeps its configured value. */
  popularity: (params: { n?: number; m?: number | null; deltas?: boolean } = {}) => {
    const query = new URLSearchParams({ n: String(params.n ?? 10) })
    if (params.m != null) query.set('m', String(params.m))
    if (params.deltas === false) query.set('deltas', 'false')
    return fetchJson<Popularity>(`/debug/popularity?${query.toString()}`)
  },

  postRating: (body: { userId: number; movieId: number; rating: number; eventId: string }) =>
    fetchJson<RatingAccepted & { detail?: string }>('/ratings', json(body)),

  ratingStatus: (eventId: string) => fetchJson<RatingStatus>(`/ratings/${encodeURIComponent(eventId)}`),

  addMovie: (body: { title: string; genres: string[] }) => fetchJson<MovieCreated>('/movies', json(body)),

  /** DELETE answers 204 with no body, so success is `status === 204`. */
  deleteMovie: (movieId: number) => fetchJson<Record<string, never>>(`/movies/${movieId}`, { method: 'DELETE' }),
}
