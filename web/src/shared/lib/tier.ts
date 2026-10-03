/** The tier banner on the user page (design D-5): plain words about why these movies are shown. */
export interface Banner {
  text: string
  /** A second sentence, when the list was topped up with popular movies. */
  extra?: string
  /** Progress towards personal suggestions; null when it is not meaningful. */
  progress: { value: number; max: number } | null
}

const FILLED_EXTRA = 'Một vài phim phổ biến được thêm vào cho đủ danh sách.'

export function bannerFor(input: {
  tier: string
  fallbackReason: string | null
  /** How many movies the user has rated (from the rating history). */
  rated: number
  /** routing.T_few_enough, from /debug/system. */
  threshold: number
}): Banner {
  const { tier, fallbackReason, rated, threshold } = input
  const progress = tier === 'enough_history' ? null : { value: Math.min(rated, threshold), max: threshold }
  const left = Math.max(threshold - rated, 0)

  let text: string
  if (fallbackReason === 'no_content_candidates') {
    text = 'Chưa tìm được phim giống phim bạn thích, nên đây là những phim được nhiều người đánh giá cao.'
  } else if (fallbackReason === 'als_artifact_missing') {
    text = `Bạn đã chấm ${rated} phim. Hệ thống chưa có hồ sơ riêng cho bạn, nên tạm gợi ý theo phim giống phim bạn thích.`
  } else if (tier === '0_history') {
    text =
      'Bạn chưa chấm phim nào. Đây là những phim được nhiều người đánh giá cao. Chấm một phim bạn đã xem để nhận gợi ý theo gu của bạn.'
  } else if (tier === 'few_history') {
    text = `Bạn đã chấm ${rated} phim. Gợi ý đang dựa trên những phim giống phim bạn thích. Chấm thêm ${left} phim để nhận gợi ý dành riêng cho bạn.`
  } else {
    text = `Gợi ý được học từ ${rated} phim bạn đã chấm và từ những người có gu giống bạn.`
  }
  return {
    text,
    extra: fallbackReason === 'filled_from_popularity' ? FILLED_EXTRA : undefined,
    progress: fallbackReason === 'als_artifact_missing' ? null : progress,
  }
}
