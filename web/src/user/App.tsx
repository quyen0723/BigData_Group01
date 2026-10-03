import { useEffect } from 'react'
import { SkipLink } from '@/shared/ui/skip-link'
import { AccountChooser } from './AccountChooser'
import { AccountProvider, useAccount } from './AccountContext'
import { Home } from './Home'

function Screen() {
  const { account } = useAccount()
  useEffect(() => {
    document.title = account ? `MovieLens — Phim dành cho ${account.name}` : 'MovieLens — Chọn tài khoản'
  }, [account])
  return (
    <>
      <SkipLink />
      {account ? <Home key={account.userId} /> : <AccountChooser />}
    </>
  )
}

export function App() {
  return (
    <AccountProvider>
      <Screen />
    </AccountProvider>
  )
}
