import { vi } from 'vitest'

/** A stand-in for the API for component and page tests: no network, every call recorded. */
export interface FakeRequest {
  method: string
  path: string // pathname + search
  body: unknown
}
export interface FakeReply {
  status: number
  body?: unknown
}
export type Handler = (req: FakeRequest) => FakeReply | Promise<FakeReply>
export type Matcher = string | RegExp

export function installFakeApi(routes: Array<[Matcher, Handler]>) {
  const calls: FakeRequest[] = []
  const stub = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, 'http://localhost')
    const req: FakeRequest = {
      method: (init?.method ?? 'GET').toUpperCase(),
      path: url.pathname + url.search,
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : undefined,
    }
    calls.push(req)
    for (const [matcher, handler] of routes) {
      const key = `${req.method} ${req.path}`
      const hit = typeof matcher === 'string' ? key === matcher : matcher.test(key)
      if (!hit) continue
      const reply = await handler(req)
      const noBody = reply.status === 204 || reply.body === undefined
      return new Response(noBody ? null : JSON.stringify(reply.body), {
        status: reply.status,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    return new Response(JSON.stringify({ detail: `no fake route for ${req.method} ${req.path}` }), { status: 404 })
  })
  vi.stubGlobal('fetch', stub)
  return {
    calls,
    callsTo: (matcher: Matcher) =>
      calls.filter((c) => (typeof matcher === 'string' ? `${c.method} ${c.path}` === matcher : matcher.test(`${c.method} ${c.path}`))),
  }
}
