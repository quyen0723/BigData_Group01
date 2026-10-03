import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Providers } from '@/shared/providers'
import { installFakeApi } from '@/test/fakeApi'
import { DemoMovies } from './DemoMovies'
import { eventLog } from './eventLog'
import { systemStatus } from './fixtures'

function setup(addReply: { status: number; body?: unknown } = { status: 201, body: { movieId: 9000002, title: 'Demo Western', genres: ['Western'], addedAt: '2026-10-03T09:00:00' } }) {
  const api = installFakeApi([
    ['GET /debug/system', () => ({ status: 200, body: systemStatus() })],
    ['POST /movies', () => addReply],
    [/^DELETE \/movies\/\d+$/, () => ({ status: 204 })],
  ])
  const onChanged = vi.fn()
  render(
    <Providers>
      <DemoMovies onChanged={onChanged} />
    </Providers>,
  )
  return { api, onChanged }
}

beforeEach(() => {
  window.sessionStorage.clear()
  eventLog.clear()
})
afterEach(() => vi.unstubAllGlobals())

describe('demo movies', () => {
  it('lists the demo movies with their id and genres', async () => {
    setup()
    expect(await screen.findByText('Demo Crime Story')).toBeInTheDocument()
    expect(screen.getByText('movieId 9000001 · Crime | Drama')).toBeInTheDocument()
  })

  it('does not delete until the confirmation dialog is accepted', async () => {
    const { api, onChanged } = setup()
    await userEvent.click(await screen.findByRole('button', { name: 'Xoá phim demo Demo Crime Story' }))

    const dialog = await screen.findByRole('alertdialog')
    expect(within(dialog).getByText(/không thể hoàn tác/)).toBeInTheDocument()
    expect(api.callsTo(/^DELETE /)).toHaveLength(0)

    await userEvent.click(within(dialog).getByRole('button', { name: 'Huỷ' }))
    expect(api.callsTo(/^DELETE /)).toHaveLength(0)

    await userEvent.click(screen.getByRole('button', { name: 'Xoá phim demo Demo Crime Story' }))
    await userEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Xoá phim' }))
    await waitFor(() => expect(api.callsTo('DELETE /movies/9000001')).toHaveLength(1))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
    expect(eventLog.getSnapshot()[0]!.text).toContain('đã xoá phim demo movieId=9000001')
  })

  it('does not send the add form without a title or genre and says what is missing', async () => {
    const { api } = setup()
    await userEvent.click(await screen.findByRole('button', { name: 'Thêm phim' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Thêm phim' }))

    expect(within(dialog).getByText('Vui lòng nhập tên phim.')).toBeInTheDocument()
    expect(within(dialog).getByText('Chọn ít nhất một thể loại.')).toBeInTheDocument()
    expect(api.callsTo('POST /movies')).toHaveLength(0)

    await userEvent.type(within(dialog).getByLabelText('Tên phim'), 'Demo Western')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Thêm phim' }))
    expect(api.callsTo('POST /movies')).toHaveLength(0)                       // still no genre
  })

  it('adds a movie with a title and genres, logs it, closes the dialog and reloads', async () => {
    const { api, onChanged } = setup()
    await userEvent.click(await screen.findByRole('button', { name: 'Thêm phim' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.type(within(dialog).getByLabelText('Tên phim'), '  Demo Western ')
    await userEvent.click(within(dialog).getByRole('checkbox', { name: 'Western' }))
    await userEvent.click(within(dialog).getByRole('checkbox', { name: 'Drama' }))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Thêm phim' }))

    await waitFor(() => expect(api.callsTo('POST /movies')).toHaveLength(1))
    expect(api.callsTo('POST /movies')[0]!.body).toEqual({ title: 'Demo Western', genres: ['Western', 'Drama'] })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(onChanged).toHaveBeenCalled()
    expect(eventLog.getSnapshot()[0]!.text).toBe('+ phim demo movieId=9000002 "Demo Western" (Western)')
  })

  it('shows the API error inside the dialog and keeps it open when the movie is refused', async () => {
    setup({ status: 422, body: { detail: 'unknown genre(s) [Foo]' } })
    await userEvent.click(await screen.findByRole('button', { name: 'Thêm phim' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.type(within(dialog).getByLabelText('Tên phim'), 'Demo')
    await userEvent.click(within(dialog).getByRole('checkbox', { name: 'Crime' }))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Thêm phim' }))

    expect(await within(dialog).findByText(/Chưa thêm được phim \(422: unknown genre/)).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(eventLog.getSnapshot()[0]).toMatchObject({ kind: 'err' })
  })

  it('toggles a genre from its label text and makes the whole row the touch target', async () => {
    setup()
    await userEvent.click(await screen.findByRole('button', { name: 'Thêm phim' }))
    const dialog = await screen.findByRole('dialog')
    const box = within(dialog).getByRole('checkbox', { name: 'Western' })
    expect(box).not.toBeChecked()
    await userEvent.click(within(dialog).getByText('Western'))
    expect(box).toBeChecked()
    const row = box.closest('label')!
    expect(row.className).toContain('min-h-11')            // 44 px on touch screens, 40 px from 640 px up
    expect(row.className).toContain('sm:min-h-10')
  })

  /** Sends a movie, abandons the request with Escape and opens the dialog again; the answer is still to come. */
  async function abandonThenReopen() {
    let answer: (reply: { status: number; body?: unknown }) => void = () => {}
    installFakeApi([
      ['GET /debug/system', () => ({ status: 200, body: systemStatus() })],
      ['POST /movies', () => new Promise((resolve) => (answer = resolve))],
    ])
    const onChanged = vi.fn()
    render(
      <Providers>
        <DemoMovies onChanged={onChanged} />
      </Providers>,
    )
    await userEvent.click(await screen.findByRole('button', { name: 'Thêm phim' }))
    const first = await screen.findByRole('dialog')
    await userEvent.type(within(first).getByLabelText('Tên phim'), 'Demo')
    await userEvent.click(within(first).getByRole('checkbox', { name: 'Crime' }))
    await userEvent.click(within(first).getByRole('button', { name: 'Thêm phim' }))
    expect(within(first).getByRole('button', { name: 'Huỷ' })).toBeDisabled()          // while sending, only Escape closes it

    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: 'Thêm phim' }))
    const second = await screen.findByRole('dialog')
    return { answer, onChanged, second }
  }

  it('does not show a refusal that belongs to an abandoned request in the dialog opened afterwards', async () => {
    const { answer, onChanged, second } = await abandonThenReopen()
    answer({ status: 422, body: { detail: 'unknown genre(s) [Foo]' } })
    await waitFor(() => expect(eventLog.getSnapshot()[0]).toMatchObject({ kind: 'err' }))   // still logged ...

    expect(within(second).queryByText(/Chưa thêm được phim/)).not.toBeInTheDocument()       // ... but not shown here
    expect(within(second).getByLabelText('Tên phim')).toHaveValue('')
    expect(within(second).getByRole('checkbox', { name: 'Crime' })).not.toBeChecked()
    expect(within(second).getByRole('button', { name: 'Thêm phim' })).toBeEnabled()
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('reloads the list but leaves the dialog opened afterwards alone when an abandoned request succeeds', async () => {
    const { answer, onChanged, second } = await abandonThenReopen()
    answer({ status: 201, body: { movieId: 9000005, title: 'Demo', genres: ['Crime'], addedAt: '2026-10-03T09:00:00' } })

    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1))                          // the movie exists: list reloads
    expect(eventLog.getSnapshot()[0]!.text).toBe('+ phim demo movieId=9000005 "Demo" (Crime)')
    expect(screen.getByRole('dialog')).toBe(second)                                          // the new dialog stays open
    expect(within(second).getByRole('button', { name: 'Thêm phim' })).toBeEnabled()
  })

  it('has labelled genre checkboxes for all 19 genres', async () => {
    setup()
    await userEvent.click(await screen.findByRole('button', { name: 'Thêm phim' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getAllByRole('checkbox')).toHaveLength(19)
  })
})
