import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { Recommendation } from '@/shared/api/types'
import type { PendingRating } from '@/shared/lib/ratingFlow'
import { Feed } from './Feed'

const rec = (rank: number, source: string): Recommendation => ({
  movieId: 100 + rank,
  title: `Movie ${rank} (199${rank % 10})`,
  genres: 'Drama',
  rank,
  score: 1 / (60 + rank),
  source,
})
const none: ReadonlyMap<number, PendingRating> = new Map()
const props = { isPending: false, isError: false, onRetry: () => {}, onRate: () => {}, pending: none }

describe('Feed', () => {
  it('shows ten skeletons while loading and marks the section busy', () => {
    const { container } = render(<Feed {...props} isPending items={undefined} />)
    expect(container.querySelector('section')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getAllByRole('listitem')).toHaveLength(10)
  })

  it('shows a single grid under the source title when every item has the same source', () => {
    render(<Feed {...props} items={[rec(1, 'content'), rec(2, 'content')]} />)
    expect(screen.getByRole('heading', { level: 2, name: 'Dành cho bạn' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: 'Giống phim bạn đã thích' })).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 3 })).toHaveLength(1 + 2)           // the group title and the two movie titles
    expect(screen.getByText('#1')).toBeInTheDocument()
    expect(screen.getByText('#2')).toBeInTheDocument()
  })

  it('splits into one row per source when there are two, keeping original ranks', () => {
    render(<Feed {...props} items={[rec(1, 'als'), rec(2, 'als'), rec(3, 'content'), rec(4, 'content')]} />)
    expect(screen.getByRole('heading', { level: 3, name: 'Dành riêng cho bạn' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: 'Giống phim bạn đã thích' })).toBeInTheDocument()
    expect(screen.getByText('#3')).toBeInTheDocument()
  })

  it('keeps the stars of a pending movie locked after a refresh moves its card to another row', () => {
    const pending = new Map<number, PendingRating>([[103, { stars: 4, phase: 'updating', eventId: 'e' }]])
    const before = [rec(1, 'content'), rec(2, 'content'), rec(3, 'content')]
    const { rerender } = render(<Feed {...props} items={before} pending={pending} />)
    expect(card('Movie 3')).toHaveTextContent('Đang cập nhật gợi ý…')

    // after the refresh movie 3 is in a different row (a new source appeared)
    const after = [rec(1, 'als'), rec(2, 'als'), rec(3, 'content')]
    rerender(<Feed {...props} items={after} pending={pending} />)
    const stars = within(card('Movie 3')).getAllByRole('radio')
    for (const s of stars) expect(s).toHaveAttribute('aria-disabled', 'true')
    expect(card('Movie 3')).toHaveTextContent('Đang cập nhật gợi ý…')
    for (const s of within(card('Movie 1')).getAllByRole('radio')) expect(s).not.toHaveAttribute('aria-disabled')
  })

  it('sends the movie id and the stars of the clicked card', async () => {
    const onRate = vi.fn()
    render(<Feed {...props} items={[rec(1, 'content'), rec(2, 'content')]} onRate={onRate} />)
    await userEvent.click(within(card('Movie 2')).getByRole('radio', { name: 'Chấm 5 sao' }))
    expect(onRate).toHaveBeenCalledWith(102, 5)
  })

  it('offers a retry when the list cannot be loaded', async () => {
    const onRetry = vi.fn()
    render(<Feed {...props} isError items={undefined} onRetry={onRetry} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Chưa tải được gợi ý.')
    await userEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(onRetry).toHaveBeenCalled()
  })

  it('says so when there is nothing to recommend', () => {
    render(<Feed {...props} items={[]} />)
    expect(screen.getByText('Hiện chưa có gợi ý nào cho bạn.')).toBeInTheDocument()
  })
})

function card(titleStart: string) {
  const heading = screen.getByRole('heading', { name: new RegExp(`^${titleStart}`) })
  return heading.closest('article')!
}
