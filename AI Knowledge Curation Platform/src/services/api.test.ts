import { describe, it, expect, vi, beforeEach } from 'vitest'

// vi.hoisted ensures this ref is available before the vi.mock factory runs
const { mockGetSession } = vi.hoisted(() => ({
  mockGetSession: vi.fn().mockResolvedValue({ data: { session: null }, error: null }),
}))

// Top-level mock — hoisted before imports, so dynamic import('./api') picks it up
vi.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: mockGetSession,
    },
  },
}))

beforeEach(() => {
  vi.resetModules()
})

describe('isDemoMode', () => {
  it('returns false initially', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
      text: () => Promise.resolve('[]'),
    }))
    const { isDemoMode } = await import('./api')
    expect(isDemoMode()).toBe(false)
  })

  it('returns true after a GET request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))
    const { api, isDemoMode } = await import('./api')
    await api.topics.list()
    expect(isDemoMode()).toBe(true)
  })
})

describe('BASE URL', () => {
  it('uses VITE_API_BASE env var instead of hardcoded localhost', async () => {
    vi.stubEnv('VITE_API_BASE', 'http://custom-api:9000')

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
      text: () => Promise.resolve('[]'),
    })
    vi.stubGlobal('fetch', fetchMock)

    const { api } = await import('./api')
    await api.topics.list()

    const calledUrl = fetchMock.mock.calls[0]?.[0] as string
    expect(calledUrl).toContain('http://custom-api:9000')
  })
})

describe('mutating actions in demo mode', () => {
  it('POST throws instead of silently returning undefined', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))
    const { api } = await import('./api')
    await api.topics.list() // triggers demo mode
    await expect(api.topics.create('test')).rejects.toThrow('Backend unavailable')
  })

  it('PATCH throws instead of silently returning undefined', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))
    const { api } = await import('./api')
    await api.topics.list() // triggers demo mode
    await expect(api.settings.update('vault', {})).rejects.toThrow('Backend unavailable')
  })

  it('DELETE throws instead of silently returning void', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))
    const { api } = await import('./api')
    await api.topics.list() // triggers demo mode
    await expect(api.topics.delete('some-id')).rejects.toThrow('Backend unavailable')
  })
})

describe('auth header injection', () => {
  it('injects Bearer token from Supabase session into GET requests', async () => {
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'test-token-abc' } },
      error: null,
    })

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
      text: () => Promise.resolve('[]'),
    })
    vi.stubGlobal('fetch', fetchMock)

    const { api } = await import('./api')
    await api.topics.list()

    const callOptions = fetchMock.mock.calls[0]?.[1] as RequestInit & { headers?: Record<string, string> }
    expect(callOptions?.headers?.['Authorization']).toBe('Bearer test-token-abc')
  })

  it('sends no Authorization header when session is null', async () => {
    mockGetSession.mockResolvedValue({
      data: { session: null },
      error: null,
    })

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
      text: () => Promise.resolve('[]'),
    })
    vi.stubGlobal('fetch', fetchMock)

    const { api } = await import('./api')
    await api.topics.list()

    const callOptions = fetchMock.mock.calls[0]?.[1] as RequestInit & { headers?: Record<string, string> }
    expect(callOptions?.headers?.['Authorization']).toBeUndefined()
  })
})
