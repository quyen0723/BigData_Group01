import type {
  DebugUser,
  MovieCreated,
  RatingAccepted,
  RatingHistory,
  RatingStatus,
  RecommendationResponse,
  SystemStatus,
} from './types'

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

  postRating: (body: { userId: number; movieId: number; rating: number; eventId: string }) =>
    fetchJson<RatingAccepted & { detail?: string }>('/ratings', json(body)),

  ratingStatus: (eventId: string) => fetchJson<RatingStatus>(`/ratings/${encodeURIComponent(eventId)}`),

  addMovie: (body: { title: string; genres: string[] }) => fetchJson<MovieCreated>('/movies', json(body)),

  /** DELETE answers 204 with no body, so success is `status === 204`. */
  deleteMovie: (movieId: number) => fetchJson<Record<string, never>>(`/movies/${movieId}`, { method: 'DELETE' }),
}
