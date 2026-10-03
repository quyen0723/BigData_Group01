export const TITLE_MAX = 200

export interface MovieFormErrors {
  title?: string
  genres?: string
}

/** The add-movie form (design D-7). The API stays the final judge: it answers 422 for an unknown genre or an empty title. */
export function validateMovie(title: string, genres: string[]): { ok: true; title: string } | { ok: false; errors: MovieFormErrors } {
  const trimmed = title.trim()
  const errors: MovieFormErrors = {}
  if (!trimmed) errors.title = 'Vui lòng nhập tên phim.'
  else if (trimmed.length > TITLE_MAX) errors.title = `Tên phim tối đa ${TITLE_MAX} ký tự.`
  if (genres.length === 0) errors.genres = 'Chọn ít nhất một thể loại.'
  return Object.keys(errors).length ? { ok: false, errors } : { ok: true, title: trimmed }
}
