import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Layout } from './Layout'
import { ToastProvider } from './Toast'

let householdSize: number
let patches: unknown[]
/** When set, PATCH /api/settings answers with this status instead of saving. */
let patchFailsWith: number | null

function mockApi() {
  householdSize = 2
  patches = []
  patchFailsWith = null
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/settings' && (!init || init.method === undefined)) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ household_size: householdSize }),
        } as Response
      }
      if (url === '/api/settings' && init?.method === 'PATCH') {
        const body = JSON.parse(init.body as string)
        if (patchFailsWith !== null) {
          return {
            ok: false,
            status: patchFailsWith,
            json: async () => ({ detail: 'Household size must be a whole number', code: 'invalid' }),
          } as Response
        }
        patches.push(body)
        householdSize = body.household_size
        return {
          ok: true,
          status: 200,
          json: async () => ({ household_size: householdSize }),
        } as Response
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response
    }),
  )
}

function renderLayout() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/planner']}>
        <ToastProvider>
          <Layout />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Renders and waits for the server value to land in the field. */
async function household(): Promise<HTMLInputElement> {
  renderLayout()
  const input = (await screen.findByLabelText(/household/i)) as HTMLInputElement
  await waitFor(() => expect(input).toHaveValue(householdSize))
  return input
}

beforeEach(mockApi)
afterEach(() => vi.unstubAllGlobals())

describe('Layout household size', () => {
  it('buffers keystrokes and commits exactly one PATCH on blur', async () => {
    const user = userEvent.setup()
    const input = await household()

    await user.clear(input)
    await user.type(input, '123')

    // Regression guard for the Task 12 buffered-input defect: not one
    // request per keystroke, and the field keeps every typed digit.
    expect(patches).toHaveLength(0)
    expect(input).toHaveValue(123)

    await user.tab() // blur
    await waitFor(() => expect(patches).toEqual([{ household_size: 123 }]))
  })

  it('commits on Enter', async () => {
    const user = userEvent.setup()
    const input = await household()

    await user.clear(input)
    await user.type(input, '5{Enter}')

    await waitFor(() => expect(patches).toEqual([{ household_size: 5 }]))
  })

  it('refuses a fractional value instead of sending a 422', async () => {
    const user = userEvent.setup()
    const input = await household()

    await user.clear(input)
    await user.type(input, '2.5')
    await user.tab()

    // The backend declares household_size as int >= 1, so 2.5 can only ever
    // come back as a 422. Never send it; revert to the server value.
    expect(patches).toHaveLength(0)
    expect(input).toHaveValue(2)
  })

  it('refuses a value below 1', async () => {
    const user = userEvent.setup()
    const input = await household()

    await user.clear(input)
    await user.type(input, '0')
    await user.tab()

    expect(patches).toHaveLength(0)
    expect(input).toHaveValue(2)
  })

  // Not covered here: commit() also normalises the draft ("04" -> "4") so a
  // no-op edit does not strand an odd-looking string in the field. jsdom's
  // number input sanitises "04", "4.0", "0004" and "1e1" down to "4"/"10" on
  // the way in, so the un-normalised draft is invisible to any DOM assertion
  // -- a test for it would pass with or without the code.

  it('surfaces a rejected save and puts the server value back', async () => {
    patchFailsWith = 422
    const user = userEvent.setup()
    const input = await household()

    await user.clear(input)
    await user.type(input, '9')
    await user.tab()

    expect(await screen.findByText(/household size must be a whole number/i)).toBeInTheDocument()
    await waitFor(() => expect(input).toHaveValue(2))
  })
})
