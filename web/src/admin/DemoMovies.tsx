import { useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus, Trash2 } from 'lucide-react'
import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { api, detailOf } from '@/shared/api/client'
import { keys } from '@/shared/api/keys'
import type { DemoMovie } from '@/shared/api/types'
import { useSystemStatus } from '@/shared/hooks/queries'
import { GENRE_NAMES } from '@/shared/lib/genre'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/shared/ui/alert-dialog'
import { Button } from '@/shared/ui/button'
import { Checkbox } from '@/shared/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/ui/dialog'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'
import { eventLog } from './eventLog'
import { TITLE_MAX, validateMovie, type MovieFormErrors } from './movieForm'

function AddMovieDialog({ open, onOpenChange, onAdded }: { open: boolean; onOpenChange: (o: boolean) => void; onAdded: () => void }) {
  const titleId = useId()
  const titleErr = useId()
  const genresErr = useId()
  const [title, setTitle] = useState('')
  const [genres, setGenres] = useState<string[]>([])
  const [errors, setErrors] = useState<MovieFormErrors>({})
  const [apiError, setApiError] = useState('')
  const [busy, setBusy] = useState(false)

  // Check the title when leaving the field, but stay quiet about an untouched empty one.
  function checkTitleOnBlur() {
    if (!title) return
    const v = validateMovie(title, ['x'])
    setErrors((x) => ({ ...x, title: v.ok ? undefined : v.errors.title }))
  }

  function reset() {
    setTitle('')
    setGenres([])
    setErrors({})
    setApiError('')
    setBusy(false)
  }

  // Every time the dialog opens or closes it is a new session. It starts clean, and an answer that belongs to an earlier
  // session (closed with Escape while sending, maybe opened again since) is logged but never shown in the current one.
  const session = useRef(0)
  useEffect(() => {
    session.current++
    if (open) reset()
  }, [open])

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    const v = validateMovie(title, genres)
    if (!v.ok) {
      setErrors(v.errors)
      return
    }
    setErrors({})
    setApiError('')
    setBusy(true)
    const mine = session.current
    const res = await api.addMovie({ title: v.title, genres })
    const current = mine === session.current
    if (res.status !== 201) {
      const detail = detailOf(res)
      eventLog.add(`✗ POST /movies -> ${res.status} ${detail}`.trim(), 'err')
      if (current) {
        setBusy(false)
        setApiError(`Chưa thêm được phim (${res.status}${detail ? `: ${detail}` : ''}).`)
      }
      return
    }
    eventLog.add(`+ phim demo movieId=${res.body.movieId} "${res.body.title}" (${res.body.genres.join('|')})`, 'ok')
    if (current) {
      setBusy(false)
      onOpenChange(false)
    }
    onAdded()                                  // the movie exists either way: reload the list
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) reset()
        onOpenChange(o)
      }}
    >
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <form onSubmit={submit} noValidate className="space-y-4">
          <DialogHeader>
            <DialogTitle>Thêm phim demo</DialogTitle>
            <DialogDescription>
              Phim chỉ nằm trong MongoDB, nhận movieId từ 9,000,000. Gợi ý xuất hiện ở hạng 3 cho user có thể loại hợp (tier few/enough).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor={titleId}>Tên phim</Label>
            <Input
              id={titleId}
              value={title}
              maxLength={TITLE_MAX}
              placeholder="Ví dụ: Demo Crime Story"
              aria-invalid={Boolean(errors.title)}
              aria-describedby={titleErr}
              onChange={(e) => setTitle(e.target.value)}
              onBlur={checkTitleOnBlur}
            />
            <p id={titleErr} role="alert" className="min-h-5 text-sm text-destructive">
              {errors.title}
            </p>
          </div>
          <fieldset className="space-y-1.5" aria-describedby={genresErr}>
            <legend className="text-sm font-medium">Thể loại</legend>
            <div className="grid grid-cols-2 gap-x-3 sm:grid-cols-3">
              {GENRE_NAMES.map((g) => {
                const id = `${titleId}-${g}`
                return (
                  // The whole row is the label, so the touch target is 44 px (40 px from 640 px up), not the 16 px box.
                  <Label key={g} htmlFor={id} className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-1 font-normal sm:min-h-10">
                    <Checkbox
                      id={id}
                      checked={genres.includes(g)}
                      onCheckedChange={(on) => setGenres((cur) => (on === true ? [...cur, g] : cur.filter((x) => x !== g)))}
                    />
                    {g}
                  </Label>
                )
              })}
            </div>
            <p id={genresErr} role="alert" className="min-h-5 text-sm text-destructive">
              {errors.genres}
            </p>
          </fieldset>
          {apiError && (
            <p role="alert" className="text-sm text-destructive">
              {apiError}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>
              Huỷ
            </Button>
            <Button type="submit" disabled={busy}>
              {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
              Thêm phim
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** The demo movies: list, add (dialog) and delete (needs confirming: it cannot be undone). `onChanged` runs after a change. */
export function DemoMovies({ onChanged }: { onChanged?: () => void }) {
  const qc = useQueryClient()
  const system = useSystemStatus()
  const [adding, setAdding] = useState(false)
  const [toDelete, setToDelete] = useState<DemoMovie | null>(null)
  const movies = system.data?.demoMovies ?? []

  function changed() {
    void qc.invalidateQueries({ queryKey: keys.system })
    onChanged?.()
  }

  async function confirmDelete() {
    const movie = toDelete
    setToDelete(null)
    if (!movie) return
    const res = await api.deleteMovie(movie.movieId)
    if (res.status !== 204) {
      eventLog.add(`✗ DELETE /movies/${movie.movieId} -> ${res.status}`, 'err')
      return
    }
    eventLog.add(`− đã xoá phim demo movieId=${movie.movieId} (rating đã có vẫn được giữ)`, 'ok')
    changed()
  }

  return (
    <section aria-labelledby="movies-title" className="space-y-3 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="movies-title" className="text-lg font-semibold">
          Phim mới (demo-only)
        </h2>
        <Button onClick={() => setAdding(true)}>
          <Plus aria-hidden="true" />
          Thêm phim
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Phim chỉ nằm trong MongoDB, nhận movieId từ 9,000,000. Gợi ý xuất hiện ở hạng 3 cho user có thể loại hợp (tier few/enough).
      </p>
      {system.isPending && <p className="text-muted-foreground">Đang tải…</p>}
      {system.data && movies.length === 0 && <p className="text-muted-foreground">Chưa có phim demo nào.</p>}
      {movies.length > 0 && (
        <ul className="divide-y rounded-lg border">
          {movies.map((m) => (
            <li key={m.movieId} className="flex items-center justify-between gap-3 px-3 py-2">
              <div className="min-w-0">
                <div className="break-words font-medium">{m.title}</div>
                <div className="font-mono text-xs text-muted-foreground">
                  movieId {m.movieId} · {m.genres.join(' | ')}
                </div>
              </div>
              <Button variant="outline" onClick={() => setToDelete(m)} aria-label={`Xoá phim demo ${m.title}`}>
                <Trash2 aria-hidden="true" />
                Xoá
              </Button>
            </li>
          ))}
        </ul>
      )}

      <AddMovieDialog open={adding} onOpenChange={setAdding} onAdded={changed} />

      <AlertDialog open={toDelete != null} onOpenChange={(o) => !o && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Xoá phim demo?</AlertDialogTitle>
            <AlertDialogDescription>
              “{toDelete?.title}” (movieId {toDelete?.movieId}) sẽ bị xoá khỏi danh mục và không thể hoàn tác. Các rating đã có vẫn được giữ.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Huỷ</AlertDialogCancel>
            <AlertDialogAction onClick={() => void confirmDelete()}>Xoá phim</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  )
}
