import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/Toast'
import { HistoryPage } from './HistoryPage'
import type { ListSummary } from '../../types'

const ENTRY: ListSummary = {
  id: 7,
  plan_id: 3,
  week_start: '2026-08-17',
  finalized_at: '2026-08-22T10:00:00',
  item_count: 10,
  checked_count: 2,
}

function mockHistory(response: () => Response) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url === '/api/lists') return response()
      return { ok: true, status: 200, json: async () => ({}) } as Response
    }),
  )
}

function ok(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ToastProvider>
          <HistoryPage />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('HistoryPage', () => {
  it('shows the empty state when no week has been finalized', async () => {
    mockHistory(() => ok([]))
    renderPage()

    expect(await screen.findByText(/nothing here yet/i)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('splits a week into bought and skipped counts', async () => {
    mockHistory(() => ok([ENTRY]))
    renderPage()

    const row = (await screen.findByRole('link', { name: /view list/i })).closest('tr')!
    const cells = row.querySelectorAll('td')
    // checked_count = 2 bought, item_count - checked_count = 8 skipped.
    expect(cells[1]).toHaveTextContent('2')
    expect(cells[2]).toHaveTextContent('8')
  })

  it('reports a failed load as an error, not as an empty history', async () => {
    mockHistory(
      () =>
        ({
          ok: false,
          status: 500,
          json: async () => ({ detail: 'Database is locked', code: 'internal' }),
        }) as Response,
    )
    renderPage()

    // "Nothing here yet" would be a false statement: the server never answered.
    expect(await screen.findByText(/couldn't load/i)).toBeInTheDocument()
    expect(screen.queryByText(/nothing here yet/i)).not.toBeInTheDocument()
  })
})
