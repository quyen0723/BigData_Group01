import {
  Baby,
  Compass,
  Drama,
  Fingerprint,
  Film,
  Ghost,
  Heart,
  Laugh,
  Moon,
  Mountain,
  Music,
  Projector,
  Rocket,
  Search,
  Shapes,
  Shield,
  Siren,
  Swords,
  Video,
  WandSparkles,
  type LucideIcon,
} from 'lucide-react'
import colors from './genre-colors.json'

export type GenreFamily = 'blue' | 'amber' | 'red' | 'violet' | 'slate' | 'rose' | 'emerald' | 'stone'

/** All 19 MovieLens genres and the placeholder, each with a colour family and an icon (design D-6).
 *  The colour is never the only signal: every tile also shows the icon and the genre name. */
export const GENRES: Record<string, { family: GenreFamily; icon: LucideIcon; label: string }> = {
  Action: { family: 'red', icon: Swords, label: 'Hành động' },
  Adventure: { family: 'emerald', icon: Compass, label: 'Phiêu lưu' },
  Animation: { family: 'amber', icon: Shapes, label: 'Hoạt hình' },
  Children: { family: 'amber', icon: Baby, label: 'Thiếu nhi' },
  Comedy: { family: 'amber', icon: Laugh, label: 'Hài' },
  Crime: { family: 'slate', icon: Fingerprint, label: 'Hình sự' },
  Documentary: { family: 'emerald', icon: Video, label: 'Tài liệu' },
  Drama: { family: 'blue', icon: Drama, label: 'Chính kịch' },
  Fantasy: { family: 'violet', icon: WandSparkles, label: 'Giả tưởng' },
  'Film-Noir': { family: 'blue', icon: Moon, label: 'Phim đen' },
  Horror: { family: 'stone', icon: Ghost, label: 'Kinh dị' },
  IMAX: { family: 'violet', icon: Projector, label: 'IMAX' },
  Musical: { family: 'rose', icon: Music, label: 'Ca nhạc' },
  Mystery: { family: 'slate', icon: Search, label: 'Bí ẩn' },
  Romance: { family: 'rose', icon: Heart, label: 'Tình cảm' },
  'Sci-Fi': { family: 'violet', icon: Rocket, label: 'Khoa học viễn tưởng' },
  Thriller: { family: 'slate', icon: Siren, label: 'Giật gân' },
  War: { family: 'red', icon: Shield, label: 'Chiến tranh' },
  Western: { family: 'red', icon: Mountain, label: 'Miền Tây' },
  '(no genres listed)': { family: 'stone', icon: Film, label: 'Chưa có thể loại' },
}

/** The 19 genres a demo movie can have (the API refuses anything else with a 422). */
export const GENRE_NAMES = Object.keys(GENRES).filter((g) => g !== '(no genres listed)')

const FALLBACK = GENRES['(no genres listed)']

export function genreInfo(genre: string) {
  return GENRES[genre] ?? FALLBACK
}

export function familyColors(family: GenreFamily): { bg: string; fg: string } {
  return colors[family]
}
