import { useId, useState, type FormEvent } from 'react'
import { PERSONA_SHORTCUTS } from './shortcuts'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'
import { RecentLog } from './LogSection'
import { navigate } from './route'
import { UserView } from './UserView'
import { useUserSession } from './useUserSession'

function UserForm({ userId }: { userId: number | null }) {
  const inputId = useId()
  const [input, setInput] = useState(userId ? String(userId) : '')

  function submit(e: FormEvent) {
    e.preventDefault()
    const v = Number.parseInt(input, 10)
    if (v > 0) navigate('users', v)
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-3 rounded-xl border bg-card p-4">
    <div className="w-44 space-y-1.5">
      <Label htmlFor={inputId}>userId</Label>
      <Input id={inputId} type="number" min={1} value={input} onChange={(e) => setInput(e.target.value)} className="font-mono" />
    </div>
    <Button type="submit">Tải gợi ý</Button>
    <div className="flex flex-wrap items-center gap-2" aria-label="Lối tắt tới các tài khoản demo">
      {PERSONA_SHORTCUTS.map((p) => (
        <Button
          key={p.userId}
          type="button"
          variant="outline"
          onClick={() => {
            setInput(String(p.userId))
            navigate('users', p.userId)
          }}
        >
          {p.label}
        </Button>
      ))}
    </div>
    </form>
  )
}

/** Inspect one user: recommendations and what is stored for them. `#/users/<id>` opens straight to a user. */
export function UsersSection({ userId }: { userId: number | null }) {
  const session = useUserSession(userId)
  return (
    <div className="space-y-4">
      {/* keyed by the user: editing the hash by hand shows that user's id in the field */}
      <UserForm key={userId ?? 'none'} userId={userId} />
      {userId == null ? <p className="text-muted-foreground">Nhập userId hoặc chọn một tài khoản demo.</p> : <UserView key={userId} session={session} />}
      <RecentLog />
    </div>
  )
}
