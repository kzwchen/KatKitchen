import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/Toast'
import { PlannerPage } from './PlannerPage'

const PLAN_SUMMARY = {
  id: 1,
  week_start: '2026-08-17',
  status: 'planning',
  meal_count: 1,
  has_list: false,
}

const COOK_MEAL = {
  id: 5,
  day: 0,
  slot: 'dinner',
  recipe_id: 10,
  recipe_name: 'Chili',
  recipe_serves: 4,
  kind: 'cook',
  servings_to_make: 4,
  servings_eaten: 2,
  source_meal_id: null,
}

let plan: typeof PLAN_SUMMARY & { meals: unknown[]; warnings: unknown[] }
let patches: any[]

function mockApi() {
  plan = { ...PLAN_SUMMARY, meals: [COOK_MEAL], warnings: [] }
  patches = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/plans' && (!init || init.method === undefined)) {
        return { ok: true, status: 200, json: async () => [PLAN_SUMMARY] } as Response
      }
      if (url === '/api/plans/1' && (!init || init.method === undefined)) {
        return { ok: true, status: 200, json: async () => plan } as Response
      }
      if (url.startsWith('/api/recipes') && (!init || init.method === undefined)) {
        return { ok: true, status: 200, json: async () => [] } as Response
      }
      if (url === '/api/meals/5' && init?.method === 'PATCH') {
        const body = JSON.parse(init.body as string)
        patches.push(body)
        plan = {
          ...plan,
          meals: [{ ...COOK_MEAL, servings_to_make: body.servings_to_make }],
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ ...COOK_MEAL, servings_to_make: body.servings_to_make }),
        } as Response
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response
    }),
  )
}

function renderPlanner() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/planner/1']}>
        <ToastProvider>
          <Routes>
            <Route path="/planner/:planId" element={<PlannerPage />} />
          </Routes>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(mockApi)
afterEach(() => vi.unstubAllGlobals())

describe('PlannerPage servings input', () => {
  it('holds every typed digit instead of snapping back mid-edit', async () => {
    const user = userEvent.setup()
    renderPlanner()

    const input = await screen.findByLabelText(/servings for chili/i)
    expect(input).toHaveValue(4)

    await user.clear(input)
    await user.type(input, '10')

    // The whole typed value must be visible immediately -- no snapping back
    // to a partial or stale digit while the field is still focused.
    expect(input).toHaveValue(10)
    // Not committed to the server yet: only blur/Enter should send a PATCH.
    expect(patches).toHaveLength(0)
  })

  it('commits exactly one PATCH on blur, not one per keystroke', async () => {
    const user = userEvent.setup()
    renderPlanner()

    const input = await screen.findByLabelText(/servings for chili/i)
    await user.clear(input)
    await user.type(input, '10')
    await user.tab() // blur

    expect(patches).toEqual([{ servings_to_make: 10 }])
  })

  it('commits on Enter', async () => {
    const user = userEvent.setup()
    renderPlanner()

    const input = await screen.findByLabelText(/servings for chili/i)
    await user.clear(input)
    await user.type(input, '6{Enter}')

    expect(patches).toEqual([{ servings_to_make: 6 }])
  })

  it('reverts to the last known-good value on blur instead of sending a non-finite amount', async () => {
    const user = userEvent.setup()
    renderPlanner()

    const input = await screen.findByLabelText(/servings for chili/i)
    await user.clear(input)
    await user.tab() // blur while empty

    expect(patches).toHaveLength(0)
    expect(input).toHaveValue(4)
  })

  it('refuses to send a value less than 1', async () => {
    const user = userEvent.setup()
    renderPlanner()

    const input = await screen.findByLabelText(/servings for chili/i)
    await user.clear(input)
    await user.type(input, '0')
    await user.tab()

    expect(patches).toHaveLength(0)
    expect(input).toHaveValue(4)
  })
})
