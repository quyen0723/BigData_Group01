import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Recommendation } from '../api/types'
import { MovieCard } from './movie-card'

const base: Recommendation = {
  movieId: 296,
  title: 'Pulp Fiction (1994)',
  genres: 'Comedy|Crime|Drama|Thriller',
  rank: 3,
  score: 0.015873,
  source: 'content',
}

describe('MovieCard', () => {
  it('shows the original rank, the title without its year, the year and at most three genres', () => {
    render(<MovieCard item={base} onRate={() => {}} />)
    expect(screen.getByText('#3')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Pulp Fiction' })).toBeInTheDocument()
    expect(screen.getByText('1994')).toBeInTheDocument()
    expect(screen.getByText('Crime')).toBeInTheDocument()
    expect(screen.queryByText('Thriller')).not.toBeInTheDocument()
  })

  it('draws the tile of the first genre with its name, not only a colour', () => {
    const { container } = render(<MovieCard item={base} onRate={() => {}} />)
    const tile = container.querySelector('[data-genre]')!
    expect(tile).toHaveAttribute('data-genre', 'Comedy')
    expect(tile).toHaveTextContent('Hài')
  })

  it('says why the movie is shown, in user language', () => {
    render(<MovieCard item={base} onRate={() => {}} />)
    expect(screen.getByText('Giống phim bạn đã thích')).toBeInTheDocument()
    expect(screen.queryByText(/content|score|nguồn/i)).not.toBeInTheDocument()
  })

  it('marks a new movie with the badge and no other card does', () => {
    const { rerender } = render(<MovieCard item={{ ...base, source: 'new' }} onRate={() => {}} />)
    expect(screen.getByText('Mới', { selector: 'span' })).toBeInTheDocument()
    rerender(<MovieCard item={base} onRate={() => {}} />)
    expect(screen.queryByText('Mới', { selector: 'span' })).not.toBeInTheDocument()
  })

  it('can hide the reason when the row title already says it', () => {
    render(<MovieCard item={base} onRate={() => {}} showReason={false} />)
    expect(screen.queryByText('Giống phim bạn đã thích')).not.toBeInTheDocument()
  })

  it('locks the stars and tells the user what is happening while a rating is pending', () => {
    render(<MovieCard item={base} pending={{ stars: 4, phase: 'updating', eventId: 'e' }} onRate={() => {}} />)
    for (const r of screen.getAllByRole('radio')) expect(r).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByText('Đang cập nhật gợi ý…')).toBeInTheDocument()
  })

  it('says the rating is being sent in the first phase', () => {
    render(<MovieCard item={base} pending={{ stars: 4, phase: 'sending', eventId: 'e' }} onRate={() => {}} />)
    expect(screen.getByText('Đang gửi đánh giá…')).toBeInTheDocument()
  })

  it('has working stars when nothing is pending', () => {
    render(<MovieCard item={base} onRate={() => {}} />)
    for (const r of screen.getAllByRole('radio')) expect(r).not.toHaveAttribute('aria-disabled')
  })

  it('shows score and the raw source label only in the technical (admin) view', () => {
    render(<MovieCard item={{ ...base, source: 'als+content' }} onRate={() => {}} technical />)
    expect(screen.getByText(/score 0\.0159/)).toBeInTheDocument()
    expect(screen.getByText(/nguồn: als\+content/i)).toBeInTheDocument()
    expect(screen.queryByText('Dành riêng cho bạn')).not.toBeInTheDocument()
  })

  it('copes with a title without a year and with no genres', () => {
    render(<MovieCard item={{ ...base, title: 'Demo Crime Story', genres: '(no genres listed)', movieId: 9000001 }} onRate={() => {}} />)
    expect(screen.getByRole('heading', { name: 'Demo Crime Story' })).toBeInTheDocument()
    expect(screen.getByText('Chưa có thể loại')).toBeInTheDocument()
  })
})
