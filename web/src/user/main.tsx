import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Providers } from '@/shared/providers'
import '@/shared/styles/index.css'
import { App } from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Providers>
      <App />
    </Providers>
  </StrictMode>,
)
