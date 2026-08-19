import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, createIngredient, getIngredients, request } from './client'

function mockFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('request', () => {
  it('returns the parsed body on success', async () => {
    mockFetch(200, { ok: true })
    await expect(request('/api/health')).resolves.toEqual({ ok: true })
  })

  it('throws an ApiError carrying the code and detail', async () => {
    mockFetch(409, { detail: "Can't delete Onion: used by Chili", code: 'ingredient_in_use' })
    const error = await request('/api/ingredients/1').catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('ingredient_in_use')
    expect((error as ApiError).message).toBe("Can't delete Onion: used by Chili")
  })

  it('falls back to a generic message when the body has no detail', async () => {
    mockFetch(500, {})
    const error = await request('/api/health').catch((e) => e)
    expect((error as ApiError).code).toBe('unknown')
    expect((error as ApiError).message).toContain('500')
  })

  it('returns undefined for a 204', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204 } as Response)
    vi.stubGlobal('fetch', fetchMock)
    await expect(request('/api/ingredients/1', { method: 'DELETE' })).resolves.toBeUndefined()
  })
})

describe('endpoint helpers', () => {
  it('passes a search term as a query parameter', async () => {
    const fetchMock = mockFetch(200, [])
    await getIngredients('oni')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/ingredients?q=oni')
  })

  it('omits the query parameter when there is no search term', async () => {
    const fetchMock = mockFetch(200, [])
    await getIngredients()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/ingredients')
  })

  it('posts JSON with the right content type', async () => {
    const fetchMock = mockFetch(201, { id: 1 })
    await createIngredient({ name: 'Onion', category: 'produce', unit: 'count' })
    const [, init] = fetchMock.mock.calls[0]
    expect(init.method).toBe('POST')
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body as string).name).toBe('Onion')
  })
})
