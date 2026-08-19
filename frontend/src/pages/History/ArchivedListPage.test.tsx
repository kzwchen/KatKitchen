import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/Toast'
import { formatWeek } from '../Planner/weeks'
import { ArchivedListPage } from './ArchivedListPage'
import type { ListItem, ShoppingList } from '../../types'

function item(over: Partial<ListItem> & { id: number; name: string }): ListItem {
  return {
    ingredient_id: over.id,
    category: 'produce',
    quantity: null,
    display_quantity: null,
    display_unit: null,
    source: 'recipe',
    section: 'buy',
    checked: false,
    note: null,
    contributions: [],
    ...over,
  }
}

/** 4 items, 2 of them checked -- exactly what the history row summarises. */
const LIST: ShoppingList = {
  id: 7,
  plan_id: 3,
  week_start: '2026-08-17',
  generated_at: '2026-08-17T09:00:00',
  finalized_at: '2026-08-22T10:00:00',
  items: [
    item({ id: 1, name: 'Carrot', display_quantity: 3, display_unit: 'count', checked: true }),
    item({ id: 2, name: 'Onion', display_quantity: 250, display_unit: 'g' }),
    item({ id: 3, name: 'Bread', category: 'bakery' }),
    item({
      id: 4,
      name: 'Salt',
      category: 'seasoning',
      section: 'staple_check',
      checked: true,
      contributions: [{ recipe_id: 10, recipe_name: 'Chili', quantity: 5 }],
    }),
  ],
}

function mockApi(list: ShoppingList) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url === '/api/lists/7') {
        return { ok: true, status: 200, json: async () => list } as Response
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response
    }),
  )
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/history/7']}>
        <ToastProvider>
          <Routes>
            <Route path="/history/:listId" element={<ArchivedListPage />} />
          </Routes>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('ArchivedListPage', () => {
  it('shows every item the history counts covered, staples included', async () => {
    mockApi(LIST)
    const { container } = renderPage()

    await screen.findByText('Carrot')
    // History summarises item_count over ALL sections, so a staple that is
    // missing here makes the summary row unreconcilable with the detail page.
    expect(screen.getByText('Salt')).toBeInTheDocument()
    expect(container.querySelectorAll('li.item')).toHaveLength(LIST.items.length)

    // 2 checked / 2 unchecked, matching checked_count and the "skipped" column.
    expect(screen.getAllByText('bought')).toHaveLength(2)
    expect(screen.getAllByText('skipped')).toHaveLength(2)
  })

  it('renders the staples under the live list heading, read-only', async () => {
    mockApi(LIST)
    renderPage()

    const heading = await screen.findByRole('heading', { name: /check your seasonings/i })
    const group = heading.closest('.aisle') as HTMLElement
    expect(within(group).getByText('Salt')).toBeInTheDocument()
    expect(within(group).getByText(/chili/i)).toBeInTheDocument()
    // An archived list is history: nothing on this page is tickable.
    expect(within(group).queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
  })

  it('formats amounts the same way the live list does', async () => {
    mockApi(LIST)
    renderPage()

    expect(await screen.findByText('3 ×')).toBeInTheDocument()
    expect(screen.getByText('250 g')).toBeInTheDocument()
  })

  it('carries a heading onto the paper copy', async () => {
    mockApi(LIST)
    const { container } = renderPage()

    await screen.findByText('Carrot')
    // The only other h1 lives in .page-head.no-print, which print.css hides.
    expect(container.querySelector('h1.print-only')).toHaveTextContent(formatWeek('2026-08-17'))
  })

  it('says so when a week had nothing to buy', async () => {
    mockApi({ ...LIST, items: [LIST.items[3]] })
    renderPage()

    expect(await screen.findByText(/nothing to buy yet/i)).toBeInTheDocument()
    // The staples still show: the week did contain something.
    expect(screen.getByText('Salt')).toBeInTheDocument()
  })
})
