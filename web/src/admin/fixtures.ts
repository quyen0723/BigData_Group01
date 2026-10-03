import type { SystemStatus } from '@/shared/api/types'

export const systemStatus = (over: Partial<SystemStatus> = {}): SystemStatus => ({
  activeVersion: 'v1.0.0',
  versions: [
    { version: 'v1.0.0', status: 'active', importedAt: '2026-09-26T15:33:14', activatedAt: '2026-09-26T15:33:14', gateChecks: [] },
    {
      version: 'v1.1.0',
      status: 'rejected',
      importedAt: '2026-09-26T15:50:00',
      activatedAt: null,
      gateChecks: [
        { name: 'G7 version numbering', passed: true, detail: 'ok' },
        { name: 'G1 candidate RMSE <= active RMSE * (1+eps)', passed: false, detail: 'RMSE computation failed: model file unreadable' },
      ],
    },
  ],
  retrainProgress: { pending: 12, nMin: 50, watermark: '2026-09-26T15:53:25' },
  demo: { ratingPollTimeoutSeconds: 60, newItemsEnabled: true, demoMovieIdStart: 9000000, tierThreshold: 10 },
  demoMovies: [{ movieId: 9000001, title: 'Demo Crime Story', genres: ['Crime', 'Drama'], addedAt: '2026-10-02T09:00:00' }],
  ...over,
})

export const recommendation = (userId: number, movies: Array<{ id: number; source?: string; rank: number }>, tier = 'few_history') => ({
  userId,
  tier,
  strategy: 'CONTENT+POPULARITY',
  modelVersion: 'v1.0.0',
  generatedAt: '2026-10-03T08:00:00Z',
  fallbackReason: null,
  recommendations: movies.map((m) => ({
    movieId: m.id,
    title: `Film ${m.id} (2000)`,
    genres: 'Crime|Drama',
    rank: m.rank,
    score: 0.016,
    source: m.source ?? 'content',
  })),
})

export const debugUser = (userId: number, interactionCount: number) => ({
  userId,
  interaction_count: interactionCount,
  recent_movieIds: [296, 318],
  positive_movieIds: [296],
  lastUpdated: '2026-10-03T07:00:00',
  pipeline: { lastBatchId: 15, lastRunAt: '2026-10-03T07:00:01' },
  modelVersion: 'v1.0.0',
})
