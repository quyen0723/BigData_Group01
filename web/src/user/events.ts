import type { RatingEvent } from '@/shared/lib/ratingFlow'

/** What the user page tells the user about a rating event (design D-5). No technical terms: no eventId, status code or batch. */
export interface Notice {
  kind: 'success' | 'error' | 'info'
  text: string
  /** Offer a "Thử lại" action that sends the same rating again. */
  retry?: boolean
  /** Which data to reload: the feed and the history (a rating was applied), or only the history. */
  refresh?: 'all' | 'history'
}

export function noticeFor(event: RatingEvent, title: string): Notice | null {
  switch (event.type) {
    case 'sending':
      return null
    case 'accepted':
      return { kind: 'success', text: `Đã lưu đánh giá ${event.stars} sao cho “${title}”` }
    case 'failed':
      return { kind: 'error', text: 'Chưa lưu được đánh giá. Vui lòng thử lại.', retry: true }
    case 'applied':
      return { kind: 'success', text: 'Gợi ý của bạn đã được cập nhật', refresh: 'all' }
    case 'timeout':
      return { kind: 'info', text: 'Đánh giá đã lưu, gợi ý sẽ cập nhật sau.', refresh: 'history' }
  }
}
