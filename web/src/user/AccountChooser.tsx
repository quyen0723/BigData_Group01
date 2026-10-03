import { Film, Loader2, UserRound } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { api } from '@/shared/api/client'
import { siblingPage } from '@/shared/lib/pages'
import { useRatingHistory } from '@/shared/hooks/queries'
import { Button } from '@/shared/ui/button'
import { Card } from '@/shared/ui/card'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'
import { pickFreshUserId, PERSONAS, validateName, type Account } from './account'
import { useAccount } from './AccountContext'

function AccountButton({ name, userId, taste }: { name: string; userId: number; taste: string }) {
  const { login } = useAccount()
  const history = useRatingHistory(userId, 1)
  const meta =
    history.data != null
      ? `${history.data.total} phim đã đánh giá · người dùng MovieLens #${userId}`
      : `Người dùng MovieLens #${userId}`
  return (
    <button
      type="button"
      onClick={() => login({ name, userId })}
      className="flex min-h-11 flex-col gap-1 rounded-xl border bg-card p-4 text-left shadow-xs transition-colors hover:border-primary hover:bg-accent"
    >
      <span className="text-xl font-semibold">{name}</span>
      <span>{taste}</span>
      <span className="text-sm text-muted-foreground">{meta}</span>
    </button>
  )
}

/** Create an account: a name and a fresh user id (design D-4). No password: demo accounts only. */
function CreateAccount() {
  const { register } = useAccount()
  const nameId = useId()
  const errId = useId()
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  function checkOnBlur() {
    // Validate when leaving the field, but stay quiet about an untouched empty field.
    if (!name) return
    const r = validateName(name)
    setError(r.ok ? '' : r.message)
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    const r = validateName(name)
    if (!r.ok) {
      setError(r.message)
      document.getElementById(nameId)?.focus()
      return
    }
    setError('')
    setBusy(true)
    const userId = await pickFreshUserId({
      hasNoRatings: async (id) => {
        const res = await api.ratingHistory(id, 1)
        return res.ok && res.body.total === 0
      },
    })
    setBusy(false)
    if (userId === null) {
      setError('Chưa tạo được tài khoản. Vui lòng thử lại.')
      return
    }
    const account: Account = { name: r.name, userId }
    register(account)
  }

  return (
    <Card className="max-w-md gap-4 p-5">
      <form onSubmit={submit} noValidate className="space-y-3">
        <h2 className="text-lg font-semibold">Tạo tài khoản mới</h2>
        <div className="space-y-1.5">
          <Label htmlFor={nameId}>Tên hiển thị</Label>
          <Input
            id={nameId}
            value={name}
            maxLength={40}
            autoComplete="off"
            aria-invalid={Boolean(error)}
            aria-describedby={errId}
            onChange={(e) => setName(e.target.value)}
            onBlur={checkOnBlur}
          />
          <p id={errId} role="alert" className="min-h-6 text-sm text-destructive">
            {error}
          </p>
        </div>
        <Button type="submit" disabled={busy}>
          {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
          Tạo tài khoản
        </Button>
      </form>
    </Card>
  )
}

export function AccountChooser() {
  const { created } = useAccount()
  return (
    <>
      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-6xl items-center gap-2 px-4 py-3 text-lg font-semibold">
          <Film className="size-5 text-primary" aria-hidden="true" />
          <span>MovieLens</span>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="mx-auto max-w-6xl space-y-8 px-4 py-8 outline-none">
        <section className="space-y-3">
          <h1 className="text-3xl font-semibold leading-tight">Chọn tài khoản để bắt đầu</h1>
          <p className="max-w-prose text-muted-foreground">
            Đây là các tài khoản demo, không có mật khẩu hay xác thực. Mỗi tài khoản gắn với một người dùng thật (đã ẩn danh)
            trong bộ dữ liệu MovieLens 32M, nên gợi ý bạn thấy là kết quả thật của hệ thống.
          </p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {PERSONAS.map((p) => (
              <AccountButton key={p.userId} {...p} />
            ))}
          </div>
        </section>

        {created.length > 0 && (
          <section className="space-y-3" aria-labelledby="mine-title">
            <h2 id="mine-title" className="text-lg font-semibold">
              Tài khoản bạn đã tạo
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {created.map((a) => (
                <AccountButton key={a.userId} name={a.name} userId={a.userId} taste="Tài khoản bạn đã tạo" />
              ))}
            </div>
          </section>
        )}

        <CreateAccount />

        <p className="text-muted-foreground">
          <UserRound className="mr-1 inline size-4" aria-hidden="true" />
          <a className="underline underline-offset-4 hover:text-primary" href={siblingPage('admin')}>
            Trang quản trị (dành cho kỹ sư)
          </a>
        </p>
      </main>
    </>
  )
}
