import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TierBanner } from './TierBanner'

describe('TierBanner', () => {
  it('explains a user with no ratings and shows 0 of the threshold', () => {
    render(<TierBanner tier="0_history" fallbackReason={null} rated={0} threshold={10} />)
    expect(screen.getByRole('status')).toHaveTextContent('Bạn chưa chấm phim nào')
    expect(screen.getByRole('progressbar', { name: 'Đã chấm 0 trên 10 phim' })).toBeInTheDocument()
    expect(screen.getByText('0/10')).toBeInTheDocument()
  })

  it('for few ratings says how many were rated and how many more unlock personal suggestions', () => {
    render(<TierBanner tier="few_history" fallbackReason={null} rated={2} threshold={10} />)
    expect(screen.getByRole('status')).toHaveTextContent('Bạn đã chấm 2 phim')
    expect(screen.getByRole('status')).toHaveTextContent('Chấm thêm 8 phim')
    expect(screen.getByText('2/10')).toBeInTheDocument()
  })

  it('has no progress bar once the user has enough ratings', () => {
    render(<TierBanner tier="enough_history" fallbackReason={null} rated={149} threshold={10} />)
    expect(screen.getByRole('status')).toHaveTextContent('149 phim')
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('explains the missing personal profile without technical words', () => {
    render(<TierBanner tier="enough_history" fallbackReason="als_artifact_missing" rated={70} threshold={10} />)
    expect(screen.getByRole('status')).toHaveTextContent('chưa có hồ sơ riêng')
    expect(screen.getByRole('status')).not.toHaveTextContent(/als|artifact|fallback/i)
  })

  it('adds the second sentence when the list was topped up with popular movies', () => {
    render(<TierBanner tier="few_history" fallbackReason="filled_from_popularity" rated={3} threshold={10} />)
    expect(screen.getByRole('status')).toHaveTextContent('phim phổ biến được thêm vào')
  })

  it('keeps its space and is an empty, busy live region while loading', () => {
    render(<TierBanner threshold={10} />)
    const region = screen.getByRole('status')
    expect(region).toHaveAttribute('aria-busy', 'true')
    expect(region).toBeEmptyDOMElement()
  })

  it('is the same live region before and after the data arrives, so the change is announced', () => {
    const { rerender } = render(<TierBanner threshold={10} />)
    const before = screen.getByRole('status')
    rerender(<TierBanner tier="few_history" fallbackReason={null} rated={2} threshold={10} />)
    expect(screen.getByRole('status')).toBe(before)
    expect(before).toHaveAttribute('aria-busy', 'false')
    expect(before).toHaveTextContent('Bạn đã chấm 2 phim')
  })
})
