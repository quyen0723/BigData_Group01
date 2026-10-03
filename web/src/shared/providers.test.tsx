import { render, screen } from '@testing-library/react'
import { useQuery } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { Providers } from './providers'

function Probe() {
  const q = useQuery({ queryKey: ['probe'], queryFn: async () => 'ready' })
  return <p>{q.data ?? 'loading'}</p>
}

describe('Providers', () => {
  it('gives children a working query client', async () => {
    render(
      <Providers>
        <Probe />
      </Providers>,
    )
    expect(await screen.findByText('ready')).toBeInTheDocument()
  })
})
