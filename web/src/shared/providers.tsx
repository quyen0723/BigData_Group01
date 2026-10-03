import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Toaster } from '@/shared/ui/sonner'
import { TooltipProvider } from '@/shared/ui/tooltip'

/** Query client defaults: data goes stale quickly (it is a live demo), no retry storms when the API is down. */
export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: 1, staleTime: 5_000, refetchOnWindowFocus: true } },
  })
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(makeQueryClient)
  return (
    <QueryClientProvider client={client}>
      <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
      <Toaster position="bottom-center" />
    </QueryClientProvider>
  )
}
