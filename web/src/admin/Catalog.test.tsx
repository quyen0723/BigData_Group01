import { act, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { makeQueryClient, Providers } from '@/shared/providers'
import { installFakeApi } from '@/test/fakeApi'
import { Catalog } from './Catalog'
import { movieList, movieRow } from './fixtures'

const PULP = movieRow(296, {
  title: 'Pulp Fiction (1994)', genres: ['Comedy', 'Crime', 'Drama', 'Thriller'], ratings: 98_425, trainRatings: 70_000, newRatings: 16, avgRating: 4.1987, wr: 4.1712,
})
const NEW_FILM = movieRow(900001, { title: 'Brand New (2019)', genres: ['Drama'], ratings: 5_000, trainRatings: 0, avgRating: null, wr: null })
const DEMO = movieRow(9_000_001, { title: 'Phim thử', genres: ['Crime', 'Drama'], ratings: 0, trainRatings: 0, avgRating: null, wr: null, isDemo: true })

type Reply = ReturnType<typeof movieList> | { status: number; body: unknown }

function params(path: string) {
  return new URLSearchParams(path.split('?')[1] ?? '')
}

function setup(reply: (p: URLSearchParams) => Reply = () => movieList([PULP, NEW_FILM, DEMO]), client?: QueryClient) {
  const api = installFakeApi([
    [
      /^GET \/movies\?/,
      (req) => {
        const out = reply(params(req.path))
        return 'status' in out ? out : { status: 200, body: out }
      },
    ],
  ])
  render(
    client ? (
      <QueryClientProvider client={client}>
        <Catalog />
      </QueryClientProvider>
    ) : (
      <Providers>
        <Catalog />
      </Providers>
    ),
  )
  return api
}

const lastParams = (api: ReturnType<typeof installFakeApi>) => params(api.callsTo(/^GET \/movies\?/).at(-1)!.path)

afterEach(() => vi.unstubAllGlobals())

describe('catalog table', () => {
  it('lists the movies with their numbers, a dash where there is no statistic, and a demo label', async () => {
    setup()
    const pulp = (await screen.findByText('Pulp Fiction (1994)')).closest('tr')!
    expect(pulp).toHaveTextContent('#296 · Comedy · Crime · Drama · Thriller')
    expect(within(pulp).getByText('98,425')).toBeInTheDocument()
    expect(within(pulp).getByText('+16 mới')).toBeInTheDocument()
    expect(within(pulp).getByText('4.199')).toBeInTheDocument()
    expect(within(pulp).getByText('4.1712')).toBeInTheDocument()

    const fresh = screen.getByText('Brand New (2019)').closest('tr')!
    expect(within(fresh).getByText('5,000')).toBeInTheDocument()
    expect(within(fresh).getAllByLabelText('chưa có số liệu')).toHaveLength(2) // average and WR
    expect(within(fresh).getAllByTitle(/phim không có rating trong tập train/)).toHaveLength(2)

    const demo = screen.getByText('Phim thử').closest('tr')!
    expect(within(demo).getByText('demo')).toBeInTheDocument()
    expect(within(pulp).queryByText('demo')).toBeNull()
  })

  it('says how many movies there are and which page this is', async () => {
    setup(() => movieList([PULP], { total: 87_585, pages: 4_380 }))
    expect(await screen.findByText('87,585 phim · trang 1/4,380')).toBeInTheDocument()
    expect(screen.getByText('Danh mục phim, 87585 kết quả, sắp theo Số rating')).toBeInTheDocument()
  })

  it('asks for the most rated first by default, 20 at a time', async () => {
    const api = setup()
    await screen.findByText('Pulp Fiction (1994)')
    const p = lastParams(api)
    expect([p.get('sort'), p.get('size'), p.get('page'), p.has('q'), p.has('genre'), p.has('order')]).toEqual(['ratings', '20', '1', false, false, false])
  })
})

describe('searching, filtering and sorting', () => {
  it('sends the search only after the typing pauses, once for the whole word', async () => {
    const api = setup()
    await screen.findByText('Pulp Fiction (1994)')
    const before = api.callsTo(/^GET \/movies\?/).length
    await userEvent.type(screen.getByLabelText('Tìm theo tên'), 'pulp')
    await waitFor(() => expect(api.callsTo(/q=pulp/)).toHaveLength(1), { timeout: 3000 })
    expect(api.callsTo(/^GET \/movies\?/).length).toBe(before + 1) // not one request per letter
    expect(api.callsTo(/q=p&|q=pu&|q=pul&/)).toHaveLength(0)
  })

  it('does not search again for a space typed after the word', async () => {
    const api = setup()
    await screen.findByText('Pulp Fiction (1994)')
    await userEvent.type(screen.getByLabelText('Tìm theo tên'), 'pulp')
    await waitFor(() => expect(api.callsTo(/q=pulp/)).toHaveLength(1), { timeout: 3000 })
    await userEvent.type(screen.getByLabelText('Tìm theo tên'), ' ')
    await new Promise((r) => setTimeout(r, 450)) // longer than the pause
    expect(api.callsTo(/q=pulp/)).toHaveLength(1) // "pulp " and "pulp" are the same search
  })

  it('filters by genre and sorts by the average, then reverses the direction', async () => {
    const api = setup()
    await screen.findByText('Pulp Fiction (1994)')
    await userEvent.selectOptions(screen.getByLabelText('Thể loại'), 'Western')
    await waitFor(() => expect(lastParams(api).get('genre')).toBe('Western'))
    await userEvent.selectOptions(screen.getByLabelText('Sắp xếp theo'), 'avg')
    await waitFor(() => expect(lastParams(api).get('sort')).toBe('avg'))
    expect(lastParams(api).has('order')).toBe(false) // the server default: descending
    await userEvent.click(screen.getByRole('button', { name: /Thứ tự: giảm dần/ }))
    await waitFor(() => expect(lastParams(api).get('order')).toBe('asc'))
    expect(screen.getByRole('button', { name: /Thứ tự: tăng dần/ })).toBeInTheDocument()
  })

  it('sorting by title starts ascending', async () => {
    setup()
    await screen.findByText('Pulp Fiction (1994)')
    await userEvent.selectOptions(screen.getByLabelText('Sắp xếp theo'), 'title')
    expect(await screen.findByRole('button', { name: /Thứ tự: tăng dần/ })).toBeInTheDocument()
  })

  it('has no choice for the average or WR when the statistics are not loaded', async () => {
    setup(() => movieList([PULP], { hasStats: false }))
    await screen.findByText('Pulp Fiction (1994)')
    expect(screen.getByRole('option', { name: 'Điểm trung bình' })).toBeDisabled()
    expect(screen.getByRole('option', { name: 'WR' })).toBeDisabled()
    expect(screen.getByRole('option', { name: 'Số rating' })).toBeEnabled()
  })
})

describe('paging', () => {
  const many = (p: URLSearchParams) => {
    const page = Number(p.get('page'))
    return movieList([movieRow(page * 10, { title: `Page ${page} movie` })], { total: 87, page, pages: 3 })
  }

  it('goes forward and back, and Trước is off on the first page', async () => {
    const api = setup(many)
    await screen.findByText('Page 1 movie')
    expect(screen.getByRole('button', { name: 'Trước' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Sau' }))
    expect(await screen.findByText('Page 2 movie')).toBeInTheDocument()
    expect(lastParams(api).get('page')).toBe('2')
    expect(screen.getByText('Trang 2 / 3')).toBeInTheDocument()
    expect(screen.getByText('87 phim · trang 2/3')).toBeInTheDocument() // the heading agrees with the pager
    await userEvent.click(screen.getByRole('button', { name: 'Sau' }))
    expect(await screen.findByText('Page 3 movie')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sau' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Trước' }))
    expect(await screen.findByText('Page 2 movie')).toBeInTheDocument()
  })

  it('goes back to page 1 when the search changes', async () => {
    const api = setup(many)
    await screen.findByText('Page 1 movie')
    await userEvent.click(screen.getByRole('button', { name: 'Sau' }))
    await screen.findByText('Page 2 movie')
    await userEvent.selectOptions(screen.getByLabelText('Thể loại'), 'Drama')
    await waitFor(() => expect(lastParams(api).get('genre')).toBe('Drama'))
    await waitFor(() => expect(lastParams(api).get('page')).toBe('1'))
    // the new genre was never asked for together with the old page number (it would be a wasted scan of the whole catalog)
    expect(api.callsTo(/genre=Drama/).filter((c) => params(c.path).get('page') !== '1')).toHaveLength(0)
  })

  it('has no pager for a single page', async () => {
    setup()
    await screen.findByText('Pulp Fiction (1994)')
    expect(screen.queryByRole('navigation', { name: 'Phân trang danh mục phim' })).toBeNull()
  })
})

describe('empty and failing', () => {
  it('says when nothing matches', async () => {
    setup(() => movieList([]))
    expect(await screen.findByText('Không có phim nào khớp.')).toBeInTheDocument()
  })

  it('shows an error with a retry that loads the table again', async () => {
    let fail = true
    const api = setup(() => (fail ? { status: 500, body: { detail: 'boom' } } : movieList([PULP])))
    const alert = await screen.findByText('Không tải được danh mục phim.', undefined, { timeout: 4000 })
    expect(alert.closest('[role="alert"]')).not.toBeNull()
    fail = false
    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: 'Thử lại' }))
    })
    expect(await screen.findByText('Pulp Fiction (1994)')).toBeInTheDocument()
    expect(api.callsTo(/^GET \/movies\?/).length).toBeGreaterThanOrEqual(2)
  })

  it('still shows the failure when a refresh fails after the table has loaded once, and keeps the old rows under it', async () => {
    let fail = false
    const client = makeQueryClient()
    client.setDefaultOptions({ queries: { ...client.getDefaultOptions().queries, staleTime: 0, retry: false } })
    setup(() => (fail ? { status: 500, body: { detail: 'boom' } } : movieList([PULP])), client)
    await screen.findByText('Pulp Fiction (1994)')
    fail = true
    act(() => {
      window.dispatchEvent(new Event('visibilitychange')) // the tab is shown again: the table refreshes
    })
    const alert = (await screen.findByText('Không tải được danh mục phim.')).closest('[role="alert"]')!
    expect(alert).toHaveTextContent('số liệu có thể đã cũ')
    expect(screen.getByText('Pulp Fiction (1994)')).toBeInTheDocument()
    fail = false
    await act(async () => {
      await userEvent.click(within(alert as HTMLElement).getByRole('button', { name: 'Thử lại' }))
    })
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
  })

  it('falls back to the rating count when the server says the statistics are not available, without an error or a second try', async () => {
    const api = setup((p) => (p.get('sort') === 'avg' ? { status: 422, body: { detail: 'average rating and WR are not available' } } : movieList([PULP])))
    await screen.findByText('Pulp Fiction (1994)')
    await userEvent.selectOptions(screen.getByLabelText('Sắp xếp theo'), 'avg')
    await waitFor(() => expect(screen.getByLabelText('Sắp xếp theo')).toHaveValue('ratings'))
    expect(await screen.findByText('Pulp Fiction (1994)')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(api.callsTo(/sort=avg/)).toHaveLength(1) // a 422 is a final answer: not asked again
  })
})
