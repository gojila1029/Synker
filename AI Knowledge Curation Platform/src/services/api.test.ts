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

  it('is exported and matches VITE_API_BASE', async () => {
    vi.stubEnv('VITE_API_BASE', 'https://my-backend.example.com')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: () => Promise.resolve('') }))
    const { BASE } = await import('./api')
    expect(BASE).toBe('https://my-backend.example.com')
  })
})

describe('mutating actions always attempt the request', () => {
  it('POST throws the real network error (not a demo-mode guard)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))
    const { api } = await import('./api')
    await api.topics.list() // puts the module into demo mode
    await expect(api.topics.create('test')).rejects.toThrow('Network error')
  })

  it('PATCH throws the real network error regardless of demo mode', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))
    const { api } = await import('./api')
    await api.topics.list() // puts the module into demo mode
    await expect(api.settings.update('vault', {})).rejects.toThrow('Network error')
  })

  it('DELETE throws the real network error regardless of demo mode', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))
    const { api } = await import('./api')
    await api.topics.list() // puts the module into demo mode
    await expect(api.topics.delete('some-id')).rejects.toThrow('Network error')
  })

  it('POST succeeds even when a prior GET failed (backend warmed up)', async () => {
    let callCount = 0
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => {
      callCount++
      if (callCount === 1) return Promise.reject(new Error('Network error')) // first GET fails
      return Promise.resolve({ ok: true, text: () => Promise.resolve(JSON.stringify({ id: '1', label: 'test' })) })
    }))
    const { api } = await import('./api')
    await api.topics.list() // GET fails, sets _isDemo = true
    const result = await api.topics.create('test') // POST should succeed
    expect(result).toMatchObject({ id: '1', label: 'test' })
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

describe('UnauthorizedError on 401', () => {
  it('is exported from api module', async () => {
    const module = await import('./api')
    expect(module.UnauthorizedError).toBeDefined()
  })

  it('POST throws UnauthorizedError when server returns 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: () => Promise.resolve('Unauthorized'),
    }))
    const { api, UnauthorizedError } = await import('./api')
    await expect(api.candidates.approve(['id-1'])).rejects.toBeInstanceOf(UnauthorizedError)
  })

  it('PATCH throws UnauthorizedError when server returns 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: () => Promise.resolve('Unauthorized'),
    }))
    const { api, UnauthorizedError } = await import('./api')
    await expect(api.settings.update('vault', {})).rejects.toBeInstanceOf(UnauthorizedError)
  })

  it('DELETE throws UnauthorizedError when server returns 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: () => Promise.resolve('Unauthorized'),
    }))
    const { api, UnauthorizedError } = await import('./api')
    await expect(api.sources.delete('src-1')).rejects.toBeInstanceOf(UnauthorizedError)
  })

  it('GET on 401 enters demo mode instead of throwing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: () => Promise.resolve('Unauthorized'),
    }))
    const { api, isDemoMode } = await import('./api')
    await expect(api.topics.list()).resolves.toBeDefined()
    expect(isDemoMode()).toBe(true)
  })
})
