import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { api } from '@/shared/api/client'
import { keys } from '@/shared/api/keys'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'
import { CaseCard } from './CaseCard'
import { caseById, CASES, SEED_USER, type CaseUser } from './caseData'
import { DemoMovies } from './DemoMovies'
import { eventLog } from './eventLog'
import { RecentLog } from './LogSection'
import { pickFreshUser } from './freshUser'
import { ModelPanel } from './ModelPanel'
import { observedText, UserView } from './UserView'
import { useUserSession } from './useUserSession'

async function resolveUser(rule: CaseUser): Promise<number | null> {
  if (rule === 'seed') return SEED_USER
  if (rule === 'fresh') {
    return pickFreshUser({
      hasHistory: async (id) => {
        const res = await api.debugUser(id)
        return res.ok && res.body.interaction_count > 0
      },
    })
  }
  return rule
}

/** The 12 case tests: pick a case, the page loads the right user, and the card says what to expect and what was observed. */
export function Cases() {
  const qc = useQueryClient()
  const selectId = useId()
  const inputId = useId()
  const [caseId, setCaseId] = useState('free')
  const [userId, setUserId] = useState<number | null>(null)
  const [input, setInput] = useState('')
  const [loadError, setLoadError] = useState('')
  const choice = useRef(0)
  const def = caseById(caseId)
  const session = useUserSession(def.kind === 'system' ? null : userId)

  // The first time the seeded user is shown with no ratings, tell the presenter how to load the demo data.
  const warnedSeed = useRef(false)
  useEffect(() => {
    if (def.user === 'seed' && session.debug.data?.interaction_count === 0 && !warnedSeed.current) {
      warnedSeed.current = true
      eventLog.add(`user ${SEED_USER} chưa có rating — chạy: python scripts/seed_demo_users.py`, 'err')
    }
  }, [def.user, session.debug.data])

  async function selectCase(id: string) {
    // Finding a fresh user takes several calls; if another case is chosen meanwhile, the slow answer is dropped.
    const mine = ++choice.current
    setCaseId(id)
    setLoadError('')
    const next = caseById(id)
    if (id !== 'free') eventLog.add(`case: ${next.label}`)
    setUserId(null)
    if (next.kind === 'system' || next.user === null) {
      setInput('')
      return
    }
    const resolved = await resolveUser(next.user)
    if (mine !== choice.current) return
    setUserId(resolved)
    setInput(resolved == null ? '' : String(resolved))
  }

  function load(e: FormEvent) {
    e.preventDefault()
    const v = Number.parseInt(input, 10)
    if (!(v > 0)) {
      setLoadError('Nhập một userId là số nguyên dương.')
      return
    }
    setLoadError('')
    choice.current++                       // a typed id wins over a case still looking for its user
    setUserId(v)
  }

  function moviesChanged() {
    session.requestDiff()
    if (userId != null) void qc.invalidateQueries({ queryKey: keys.adminRecs(userId) })
  }

  return (
    <div className="space-y-4">
      <form onSubmit={load} className="flex flex-wrap items-end gap-3 rounded-xl border bg-card p-4">
        <div className="min-w-0 flex-1 basis-64 space-y-1.5">
          <Label htmlFor={selectId}>Case test</Label>
          <select
            id={selectId}
            value={caseId}
            onChange={(e) => void selectCase(e.target.value)}
            className="h-11 w-full rounded-md border border-input bg-card px-3 text-sm sm:h-10"
          >
            {CASES.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
        <div className="w-40 space-y-1.5">
          <Label htmlFor={inputId}>userId</Label>
          <Input
            id={inputId}
            type="number"
            min={1}
            value={input}
            aria-invalid={Boolean(loadError)}
            aria-describedby={`${inputId}-err`}
            onChange={(e) => setInput(e.target.value)}
            className="font-mono"
          />
        </div>
        <Button type="submit">Tải gợi ý</Button>
        <p id={`${inputId}-err`} role="alert" className="basis-full text-sm text-destructive empty:hidden">
          {loadError}
        </p>
      </form>

      <CaseCard def={def} observed={def.kind === 'system' ? 'Quan sát: —' : observedText(session)} />

      {def.movies && <DemoMovies onChanged={moviesChanged} />}
      {def.kind === 'system' && <ModelPanel />}

      {def.kind !== 'system' &&
        (userId == null ? (
          <p className="text-muted-foreground">{caseId === 'free' ? 'Chọn một case test để bắt đầu, hoặc nhập userId rồi bấm Tải gợi ý.' : 'Nhập userId rồi bấm Tải gợi ý.'}</p>
        ) : (
          <UserView session={session} />
        ))}

      <RecentLog />
    </div>
  )
}
