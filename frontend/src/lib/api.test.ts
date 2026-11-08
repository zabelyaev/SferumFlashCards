import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('API client', () => {
  it('sends catalog filters as query parameters', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) => new Response(JSON.stringify({ items: [], total: 0 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await api.getCatalog({ search: 'квадратные уравнения', subject: 'algebra', page: 2, limit: 10 })

    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/decks?')
    expect(String(url)).toContain('search=%D0%BA%D0%B2%D0%B0%D0%B4%D1%80%D0%B0%D1%82%D0%BD%D1%8B%D0%B5')
    expect(String(url)).toContain('subject=algebra')
    expect(String(url)).toContain('page=2')
    expect(String(url)).toContain('limit=10')
  })

  it('opens a server study session for the selected deck', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) =>
      new Response(JSON.stringify({ session: null, reason: 'nothing_due' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await api.openStudySession('42')

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/study/sessions')
    expect(JSON.parse(String(init?.body))).toEqual({ deck_id: 42 })
  })

  it('rejects non-numeric study deck IDs without making a request', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    expect(() => api.openStudySession('all')).toThrow('выберите одну колоду')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('submits a server review with the current answer token', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify({ session: { id: 8 } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await api.submitStudyReview('8', {
      card_id: 101,
      rating: 3,
      answer_token: 'signed-token',
    })

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/study/sessions/8/reviews')
    expect(JSON.parse(String(init?.body))).toEqual({
      card_id: 101,
      rating: 3,
      answer_token: 'signed-token',
    })
  })

  it('accepts empty 204 responses', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.removeFromLibrary('42')).resolves.toBeUndefined()
  })

  it('turns validation details into a readable API error', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL) => new Response(JSON.stringify({
      detail: [{ loc: ['body', 'title'], msg: 'Field required', type: 'missing' }],
    }), {
      status: 422,
      headers: { 'Content-Type': 'application/json' },
    })))

    await expect(api.getProfile()).rejects.toMatchObject({
      message: 'Field required',
      status: 422,
    })
  })

  it('shows a useful message when a proxy returns a plain-text error', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL) =>
      new Response('TLS certificate has expired', { status: 500, headers: { 'Content-Type': 'text/plain' } }),
    ))

    await expect(api.getProfile()).rejects.toMatchObject({
      message: 'TLS certificate has expired',
      status: 500,
    })
  })

  it('identifies an empty server error as an API or proxy failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL) =>
      new Response(null, { status: 500 }),
    ))

    await expect(api.getProfile()).rejects.toMatchObject({
      message: 'Сервер API или прокси вернул ошибку (500). Проверьте консоль Vite.',
      status: 500,
    })
  })
})
