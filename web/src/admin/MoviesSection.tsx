import { useQueryClient } from '@tanstack/react-query'
import { Catalog } from './Catalog'
import { DemoMovies } from './DemoMovies'

/** The admin "Phim" section: the demo-movie panel (add, delete) and below it the searchable catalog of every movie. A change to the demo
 *  movies reloads the catalog (the server also drops its cached copy at once). */
export function MoviesSection() {
  const qc = useQueryClient()
  return (
    <div className="space-y-4">
      <DemoMovies onChanged={() => void qc.invalidateQueries({ queryKey: ['movies'] })} />
      <Catalog />
    </div>
  )
}
