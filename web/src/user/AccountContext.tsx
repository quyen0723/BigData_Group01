import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import {
  addCreated,
  clearSession,
  readCreated,
  readSession,
  safeStore,
  saveSession,
  type Account,
  type SafeStore,
} from './account'

/** The signed-in demo account and the accounts created in this browser. App-wide and rarely changing, so it is a
 *  Context; data from the API is not (it goes through TanStack Query). */
interface AccountState {
  account: Account | null
  created: Account[]
  login(account: Account): void
  logout(): void
  /** Remember a newly created account and sign in with it. */
  register(account: Account): void
  /** True when the account was chosen on this page; false when a saved session was restored on load. */
  signedInHere: boolean
}

const Ctx = createContext<AccountState | null>(null)

export function AccountProvider({ children, store: given }: { children: ReactNode; store?: SafeStore }) {
  const store = useMemo(() => given ?? safeStore(), [given])
  const [account, setAccount] = useState<Account | null>(() => readSession(store))
  const [created, setCreated] = useState<Account[]>(() => readCreated(store))
  const [signedInHere, setSignedInHere] = useState(false)

  const login = useCallback(
    (next: Account) => {
      saveSession(store, next)
      setAccount(next)
      setSignedInHere(true)
    },
    [store],
  )
  const logout = useCallback(() => {
    clearSession(store)
    setAccount(null)
    setSignedInHere(false)
    setCreated(readCreated(store))
  }, [store])
  const register = useCallback(
    (next: Account) => {
      setCreated(addCreated(store, next))
      login(next)
    },
    [store, login],
  )

  const value = useMemo(
    () => ({ account, created, login, logout, register, signedInHere }),
    [account, created, login, logout, register, signedInHere],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAccount(): AccountState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAccount must be used inside <AccountProvider>')
  return v
}
