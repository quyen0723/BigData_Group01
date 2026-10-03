const TRAILING_YEAR = /\s*\((\d{4})\)\s*$/

/** "Pulp Fiction (1994)" -> { title: "Pulp Fiction", year: 1994 }. A title without a trailing year keeps its text and has no year. */
export function splitYear(raw: string): { title: string; year: number | null } {
  const m = TRAILING_YEAR.exec(raw)
  if (!m) return { title: raw.trim(), year: null }
  return { title: raw.slice(0, m.index).trim(), year: Number(m[1]) }
}

/** MovieLens stores genres as "Crime|Drama". The placeholder "(no genres listed)" counts as none. */
export function splitGenres(genres: string): string[] {
  return genres
    .split('|')
    .map((g) => g.trim())
    .filter((g) => g && g !== '(no genres listed)')
}

export function primaryGenre(genres: string): string {
  return splitGenres(genres)[0] ?? '(no genres listed)'
}
