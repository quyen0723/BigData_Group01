import { render, screen, waitFor, within, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Providers } from '@/shared/providers'
import { installFakeApi } from '@/test/fakeApi'
import { App } from './App'
import { debugUser, recommendation, systemStatus } from './fixtures'
import { eventLog } from './eventLog'

function api(over: Parameters<typeof systemStatus>[0] = {}) {
  return installFakeApi([
    ['GET /debug/system', () => ({ status: 200, body: systemStatus(over) })],
    ['GET /health', () => ({ status: 200, body: { status: 'ok' } })],
    [/^GET \/recommendations\/591751/, () => ({ status: 200, body: recommendation(591751, [{ id: 99, rank: 1 }, { id: 108, rank: 2 }]) })],
    [/^GET \/debug\/users\/591751$/, () => ({ status: 200, body: debugUser(591751, 2) })],
  ])
}

function mount(hash: string) {
  window.location.hash = hash
  return render(
    <Providers>
      <App />
    </Providers>,
  )
}

beforeEach(() => {
  window.sessionStorage.clear()
  eventLog.clear()
})
afterEach(() => {
  vi.unstubAllGlobals()
  window.location.hash = ''
})

describe('admin shell', () => {
  it('has the seven sections in the sidebar and marks the open one', async () => {
    api()
    mount('#/overview')
    const nav = screen.getByRole('navigation', { name: 'Các mục quản trị' })
    for (const name of ['Tổng quan', 'Case test', 'Người dùng', 'Phim', 'Phổ biến', 'Model', 'Nhật ký']) {
      expect(within(nav).getByRole('link', { name })).toBeInTheDocument()
    }
    expect(within(nav).getByRole('link', { name: 'Tổng quan' })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).getByRole('link', { name: 'Case test' })).not.toHaveAttribute('aria-current')
  })

  it('opens the section named by the hash, including a user', async () => {
    api()
    mount('#/users/591751')
    expect(await screen.findByRole('heading', { level: 1, name: 'Người dùng' })).toBeInTheDocument()
    expect(await screen.findByText('Film 99')).toBeInTheDocument()
    expect(screen.getByLabelText('userId')).toHaveValue(591751)
    expect(document.title).toBe('MovieLens — Quản trị — Người dùng')
  })

  it('shows the overview for an empty or unknown hash', async () => {
    api()
    mount('#/nope')
    expect(screen.getByRole('heading', { level: 1, name: 'Tổng quan' })).toBeInTheDocument()
    expect(await screen.findByText('v1.0.0', { selector: 'div' })).toBeInTheDocument()
  })

  it('follows a hash change without a reload', async () => {
    api()
    mount('#/overview')
    act(() => {
      window.location.hash = '#/models'
      window.dispatchEvent(new HashChangeEvent('hashchange'))
    })
    expect(await screen.findByRole('heading', { level: 1, name: 'Model' })).toBeInTheDocument()
    expect(await screen.findByText('v1.1.0')).toBeInTheDocument()
  })

  it('shows the serving model and a link to the user page in the header', async () => {
    api()
    mount('#/overview')
    expect(await screen.findByText('model v1.0.0')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Mở trang người dùng' })).toHaveAttribute('href', '/app')
  })

  it('overview shows the live numbers from the API', async () => {
    api()
    mount('#/overview')
    expect(await screen.findByText('2 version: 1 active, 1 rejected')).toBeInTheDocument()
    expect(await screen.findByText('ok')).toBeInTheDocument()                    // GET /health
    expect(screen.getByText('12 / 50', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('Số rating để user rời tier few_history')).toBeInTheDocument()
  })

  it('model section shows every gate check with PASS or FAIL and the reason of a failure', async () => {
    api()
    mount('#/models')
    expect(await screen.findByText('1/2 đạt')).toBeInTheDocument()
    expect(screen.getByText('PASS')).toBeInTheDocument()
    expect(screen.getByText('FAIL')).toBeInTheDocument()
    expect(screen.getByText(/model file unreadable/)).toBeInTheDocument()
    expect(screen.getByText('rejected')).toBeInTheDocument()
    expect(screen.getByText('active')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: /Tiến độ retrain: 12 trên 50/ })).toBeInTheDocument()
  })

  it('log section lists events newest first, with times, and can be cleared', async () => {
    api()
    eventLog.add('first event')
    eventLog.add('second event', 'ok')
    mount('#/log')
    const log = await screen.findByRole('log', { name: 'Nhật ký sự kiện' })
    const items = within(log).getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('second event')
    expect(items[1]).toHaveTextContent('first event')
    expect(items[0]).toHaveTextContent(/\[\d\d:\d\d:\d\d\.\d{3}\]/)
    await userEvent.click(screen.getByRole('button', { name: /Xoá nhật ký/ }))
    await waitFor(() => expect(screen.getByText(/Chưa có sự kiện nào/)).toBeInTheDocument())
  })
})

describe('admin shell on a narrow screen', () => {
  it('opens the sidebar as a drawer and closes it when a section is chosen', async () => {
    const original = window.innerWidth
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 800 })
    try {
      api()
      mount('#/overview')
      expect(screen.queryByRole('navigation', { name: 'Các mục quản trị' })).not.toBeInTheDocument()       // drawer closed

      await userEvent.click(screen.getByRole('button', { name: 'Mở hoặc đóng menu' }))
      const nav = await screen.findByRole('navigation', { name: 'Các mục quản trị' })
      expect(within(nav).getByRole('link', { name: 'Tổng quan' })).toHaveAttribute('aria-current', 'page')

      await userEvent.click(within(nav).getByRole('link', { name: 'Case test' }))
      await act(async () => {
        window.dispatchEvent(new HashChangeEvent('hashchange'))
      })
      expect(await screen.findByRole('heading', { level: 1, name: 'Case test' })).toBeInTheDocument()
      await waitFor(() => expect(screen.queryByRole('navigation', { name: 'Các mục quản trị' })).not.toBeInTheDocument())
    } finally {
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: original })
    }
  })
})
