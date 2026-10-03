import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { ApiError } from '@/shared/api/client'
import { Toaster } from '@/shared/ui/sonner'
import { TooltipProvider } from '@/shared/ui/tooltip'

/** A 4xx answer is the API's final word on this request (a bad parameter, a feature that is off): asking again gives the same answer. */
const retryOnce = (failures: number, error: Error) => failures < 1 && !(error instanceof ApiError && error.status >= 400 && error.status < 500)

/** Query client defaults: data goes stale quickly (it is a live demo), no retry storms when the API is down. */
export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: retryOnce, staleTime: 5_000, refetchOnWindowFocus: true } },
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
