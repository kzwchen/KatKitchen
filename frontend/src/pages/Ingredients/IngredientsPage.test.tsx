import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/Toast'
import { IngredientsPage } from './IngredientsPage'
import type { Ingredient } from '../../types'

let ingredients: Ingredient[] = []
let nextId = 1

function mockApi() {
  ingredients = [{ id: nextId++, name: 'Carrot', category: 'produce', unit: 'count', is_staple: false, usage_count: 0 }]
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith('/api/ingredients') && (!init || init.method === undefined)) {
        const match = /[?&]q=([^&]*)/.exec(url)
        const q = match ? decodeURIComponent(match[1]).toLowerCase() : ''
        const filtered = q
          ? ingredients.filter((i) => i.name.toLowerCase().includes(q))
          : ingredients
        return { ok: true, status: 200, json: async () => filtered } as Response
      }
      if (url === '/api/ingredients' && init?.method === 'POST') {
        const body = JSON.parse(init.body as string)
        const created: Ingredient = { ...body, id: nextId++, usage_count: 0 }
        ingredients = [...ingredients, created]
        return { ok: true, status: 201, json: async () => created } as Response
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response
    }),
  )
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <IngredientsPage />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

beforeEach(mockApi)
afterEach(() => vi.unstubAllGlobals())

describe('IngredientsPage', () => {
  it('shows a newly created ingredient that matches the active search filter', async () => {
    const user = userEvent.setup()
    renderPage()

    // Wait for the initial (unfiltered) load, then filter to a search term
    // that "Carrot" does not match but the ingredient we're about to create
    // does -- reproducing the exact repro steps from the finding.
    await screen.findByText('Carrot')
    await user.type(screen.getByPlaceholderText(/search ingredients/i), 'on')
    expect(screen.queryByText('Carrot')).not.toBeInTheDocument()

    await user.type(screen.getByLabelText(/^name$/i), 'Onion')
    await user.click(screen.getByRole('button', { name: /add ingredient/i }))

    // No refocus, no remount: the filtered ['ingredients', 'on'] query must
    // be invalidated by the create mutation for this to appear.
    expect(await screen.findByText('Onion')).toBeInTheDocument()
  })
})
