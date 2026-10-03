import { render, screen } from '@testing-library/react'
import { useState } from 'react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { StarRating } from './star-rating'

describe('StarRating', () => {
  it('is a radio group with a name and five stars', () => {
    render(<StarRating label="Chấm sao cho Pulp Fiction" onRate={() => {}} />)
    expect(screen.getByRole('radiogroup', { name: 'Chấm sao cho Pulp Fiction' })).toBeInTheDocument()
    expect(screen.getAllByRole('radio')).toHaveLength(5)
    expect(screen.getByRole('radio', { name: 'Chấm 4 sao' })).toBeInTheDocument()
  })

  it('sends the chosen number of stars on click', async () => {
    const onRate = vi.fn()
    render(<StarRating label="x" onRate={onRate} />)
    await userEvent.click(screen.getByRole('radio', { name: 'Chấm 4 sao' }))
    expect(onRate).toHaveBeenCalledWith(4)
  })

  it('reaches the group with one Tab stop and moves with the arrow keys without rating', async () => {
    const onRate = vi.fn()
    render(<StarRating label="x" onRate={onRate} />)
    const radios = screen.getAllByRole('radio')
    expect(radios.filter((r) => r.getAttribute('tabindex') === '0')).toHaveLength(1)

    await userEvent.tab()
    expect(radios[0]).toHaveFocus()
    await userEvent.keyboard('{ArrowRight}{ArrowRight}')
    expect(radios[2]).toHaveFocus()
    await userEvent.keyboard('{ArrowLeft}')
    expect(radios[1]).toHaveFocus()
    await userEvent.keyboard('{End}')
    expect(radios[4]).toHaveFocus()
    await userEvent.keyboard('{Home}')
    expect(radios[0]).toHaveFocus()
    expect(onRate).not.toHaveBeenCalled()
  })

  it('wraps around at the ends, like an ARIA radio group', async () => {
    render(<StarRating label="x" onRate={() => {}} />)
    const radios = screen.getAllByRole('radio')
    await userEvent.tab()
    await userEvent.keyboard('{ArrowLeft}')
    expect(radios[4]).toHaveFocus()
    await userEvent.keyboard('{ArrowRight}')
    expect(radios[0]).toHaveFocus()
  })

  it('keeps keyboard focus on the star that was used while the rating is being sent', async () => {
    function Harness() {
      const [busy, setBusy] = useState(false)
      return <StarRating label="x" onRate={() => setBusy(true)} disabled={busy} chosen={busy ? 4 : null} />
    }
    render(<Harness />)
    await userEvent.tab()
    await userEvent.keyboard('{ArrowRight}{ArrowRight}{ArrowRight}{Enter}')
    const fourth = screen.getByRole('radio', { name: 'Chấm 4 sao' })
    expect(fourth).toHaveAttribute('aria-disabled', 'true')
    expect(fourth).toHaveFocus()                                   // a natively disabled button would have dropped focus to <body>
  })

  it('rates with Enter or Space on the focused star', async () => {
    const onRate = vi.fn()
    render(<StarRating label="x" onRate={onRate} />)
    await userEvent.tab()
    await userEvent.keyboard('{ArrowRight}{Enter}')
    expect(onRate).toHaveBeenLastCalledWith(2)
    await userEvent.keyboard('{ArrowRight} ')
    expect(onRate).toHaveBeenLastCalledWith(3)
  })

  it('cannot be used while disabled and shows the value that is being sent', async () => {
    const onRate = vi.fn()
    render(<StarRating label="x" onRate={onRate} disabled chosen={4} />)
    const radios = screen.getAllByRole('radio')
    for (const r of radios) expect(r).toHaveAttribute('aria-disabled', 'true')
    expect(radios[3]).toHaveAttribute('aria-checked', 'true')
    await userEvent.click(radios[1]!)
    expect(onRate).not.toHaveBeenCalled()
  })
})
