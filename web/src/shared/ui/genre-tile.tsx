import { familyColors, genreInfo } from '../lib/genre'
import { primaryGenre } from '../lib/movie'
import { cn } from '../lib/utils'

/** The "poster" of a movie card: MovieLens has no images, so each card gets a tile coloured by the family of its first
 *  genre, with that genre's icon and name. Colour is never the only signal (design D-6). */
export function GenreTile({ genres, className }: { genres: string; className?: string }) {
  const genre = primaryGenre(genres)
  const { family, icon: Icon, label } = genreInfo(genre)
  const { bg, fg } = familyColors(family)
  return (
    <div
      className={cn('flex h-24 flex-col items-center justify-center gap-1 rounded-t-[inherit]', className)}
      style={{ backgroundColor: bg, color: fg }}
      data-genre={genre}
      data-family={family}
    >
      <Icon className="size-8" aria-hidden="true" strokeWidth={1.75} />
      <span className="px-2 text-center text-sm font-medium leading-tight">{label}</span>
    </div>
  )
}
