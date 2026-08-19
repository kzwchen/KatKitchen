import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/Toast'
import { RecipeEditorPage } from './RecipeEditorPage'

const ONION = {
  id: 1,
  name: 'Onion',
  category: 'produce',
  unit: 'count',
  is_staple: false,
  usage_count: 0,
}
const CHICKEN = {
  id: 2,
  name: 'Chicken thigh',
  category: 'meat_seafood',
  unit: 'g',
  is_staple: false,
  usage_count: 0,
}

let posted: any[] = []

function mockApi() {
  posted = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith('/api/ingredients') && (!init || init.method === undefined)) {
        return { ok: true, status: 200, json: async () => [ONION, CHICKEN] } as Response
      }
      if (url === '/api/ingredients' && init?.method === 'POST') {
        const body = JSON.parse(init.body as string)
        return {
          ok: true,
          status: 201,
          json: async () => ({ ...body, id: 3, usage_count: 0 }),
        } as Response
      }
      if (url === '/api/recipes' && init?.method === 'POST') {
        posted.push(JSON.parse(init.body as string))
        return { ok: true, status: 201, json: async () => ({ id: 7, lines: [] }) } as Response
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response
    }),
  )
}

function renderEditor() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/recipes/new']}>
        <ToastProvider>
          <Routes>
            <Route path="/recipes/new" element={<RecipeEditorPage />} />
            <Route path="/recipes" element={<p>Recipe list</p>} />
          </Routes>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(mockApi)
afterEach(() => vi.unstubAllGlobals())

describe('RecipeEditorPage', () => {
  it('constrains the unit choices to the selected ingredient family', async () => {
    const user = userEvent.setup()
    renderEditor()

    await user.click(screen.getByRole('button', { name: /add ingredient line/i }))
    await user.type(screen.getByPlaceholderText(/search ingredients/i), 'chick')
    await user.click(await screen.findByRole('option', { name: /chicken thigh/i }))

    const unitSelect = screen.getByLabelText(/unit for chicken thigh/i)
    const options = within(unitSelect).getAllByRole('option').map((o) => o.textContent)
    expect(options).toEqual(['g', 'kg', 'oz', 'lb'])
  })

  it('shows a plain whole-number field for a count ingredient', async () => {
    const user = userEvent.setup()
    renderEditor()

    await user.click(screen.getByRole('button', { name: /add ingredient line/i }))
    await user.type(screen.getByPlaceholderText(/search ingredients/i), 'onio')
    // NOTE: brief said `/^onion$/i` here, but the option renders as "Onion · count"
    // (the picker appends the unit), so an end-anchored regex cannot match.
    // Anchored at the start only, per the task's correction.
    await user.click(await screen.findByRole('option', { name: /^onion/i }))

    expect(screen.queryByLabelText(/unit for onion/i)).not.toBeInTheDocument()
    expect(screen.getByText('whole')).toBeInTheDocument()
  })

  it('offers inline creation when the typed name matches nothing', async () => {
    const user = userEvent.setup()
    renderEditor()

    await user.click(screen.getByRole('button', { name: /add ingredient line/i }))
    await user.type(screen.getByPlaceholderText(/search ingredients/i), 'Tahini')
    await user.click(await screen.findByRole('option', { name: /create "Tahini"/i }))

    expect(screen.getByRole('form', { name: /new ingredient/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/^name$/i)).toHaveValue('Tahini')
  })

  it('selects a newly created ingredient into the line it was created from', async () => {
    const user = userEvent.setup()
    renderEditor()

    await user.click(screen.getByRole('button', { name: /add ingredient line/i }))
    await user.type(screen.getByPlaceholderText(/search ingredients/i), 'Tahini')
    await user.click(await screen.findByRole('option', { name: /create "Tahini"/i }))
    await user.click(screen.getByRole('button', { name: /add ingredient$/i }))

    expect(await screen.findByText('Tahini')).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: /new ingredient/i })).not.toBeInTheDocument()
  })

  it('submits the typed display unit rather than a converted amount', async () => {
    const user = userEvent.setup()
    renderEditor()

    await user.type(screen.getByLabelText(/recipe name/i), 'Roast chicken')
    await user.clear(screen.getByLabelText(/serves/i))
    await user.type(screen.getByLabelText(/serves/i), '4')

    await user.click(screen.getByRole('button', { name: /add ingredient line/i }))
    await user.type(screen.getByPlaceholderText(/search ingredients/i), 'chick')
    await user.click(await screen.findByRole('option', { name: /chicken thigh/i }))
    await user.type(screen.getByLabelText(/quantity for chicken thigh/i), '1')
    await user.selectOptions(screen.getByLabelText(/unit for chicken thigh/i), 'kg')

    await user.click(screen.getByRole('button', { name: /save recipe/i }))

    expect(posted).toHaveLength(1)
    expect(posted[0].name).toBe('Roast chicken')
    expect(posted[0].serves).toBe(4)
    expect(posted[0].lines).toEqual([
      { ingredient_id: 2, quantity: 1, display_unit: 'kg', prep_note: null },
    ])
  })

  it('refuses to save a line with no ingredient chosen', async () => {
    const user = userEvent.setup()
    renderEditor()

    await user.type(screen.getByLabelText(/recipe name/i), 'Empty')
    await user.click(screen.getByRole('button', { name: /add ingredient line/i }))
    await user.click(screen.getByRole('button', { name: /save recipe/i }))

    expect(posted).toHaveLength(0)
    expect(screen.getByText(/pick an ingredient for every line/i)).toBeInTheDocument()
  })
})
