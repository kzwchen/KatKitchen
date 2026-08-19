import { useParams } from 'react-router-dom'
import {
  addListItem,
  deleteListItem,
  finalizeList,
  generateList,
  updateListItem,
} from '../../api/client'
import { keys, useInvalidatingMutation, useList, useSuggestions } from '../../api/hooks'
import { useToast } from '../../components/Toast'
import { CATEGORY_LABELS } from '../../types'
import type { Category, ListItem } from '../../types'
import { formatWeek } from '../Planner/weeks'
import { ManualAdd } from './ManualAdd'

/** Chunk consecutive runs of the same category. The API already ordered them. */
export function groupByCategory(
  items: ListItem[],
): { category: Category | null; label: string; items: ListItem[] }[] {
  const groups: { category: Category | null; label: string; items: ListItem[] }[] = []
  for (const item of items) {
    const last = groups[groups.length - 1]
    if (last && last.category === item.category) {
      last.items.push(item)
    } else {
      groups.push({
        category: item.category,
        label: item.category ? CATEGORY_LABELS[item.category] : 'Other items',
        items: [item],
      })
    }
  }
  return groups
}

/** "3 ×" / "250 g" / "" -- shared with the archived (read-only) list view. */
export function amountOf(item: ListItem): string {
  if (item.display_quantity == null) return ''
  if (item.display_unit === 'count') return `${item.display_quantity} ×`
  return `${item.display_quantity} ${item.display_unit}`
}

function why(item: ListItem): string | undefined {
  if (item.contributions.length === 0) return undefined
  return item.contributions
    .map((c) => `${c.recipe_name}: ${Math.round(c.quantity * 100) / 100}`)
    .join('\n')
}

export function ShoppingListPage() {
  const planId = Number(useParams().planId)
  const { data: list, isLoading, error } = useList(planId)
  const { data: suggestions = [] } = useSuggestions(list?.id)
  const toast = useToast()

  const invalidate = [keys.list(planId), keys.plans(), keys.history()]
  const check = useInvalidatingMutation(
    (args: { itemId: number; checked: boolean }) =>
      updateListItem(list!.id, args.itemId, { checked: args.checked }),
    invalidate,
  )
  const drop = useInvalidatingMutation(
    (itemId: number) => deleteListItem(list!.id, itemId),
    invalidate,
  )
  const accept = useInvalidatingMutation(
    (args: { ingredientId: number | null; name: string }) =>
      addListItem(list!.id, {
        ingredient_id: args.ingredientId,
        custom_name: args.ingredientId ? null : args.name,
      }),
    [...invalidate, ...(list ? [keys.suggestions(list.id)] : [])],
  )
  const regenerate = useInvalidatingMutation(() => generateList(planId), invalidate)
  const finish = useInvalidatingMutation(() => finalizeList(list!.id), invalidate)

  async function run(action: Promise<unknown>) {
    try {
      await action
    } catch (err) {
      toast.showError(err)
    }
  }

  if (isLoading) return <p className="muted">Loading…</p>
  if (error || !list) {
    return (
      <section>
        <h1>Shopping list</h1>
        <p className="muted">
          No list for this week yet. Generate one from the planner.
        </p>
      </section>
    )
  }

  const buy = list.items.filter((item) => item.section === 'buy')
  const staples = list.items.filter((item) => item.section === 'staple_check')

  return (
    <section className="shopping">
      <div className="page-head no-print">
        <h1>Shopping list — {formatWeek(list.week_start)}</h1>
        <div className="page-head__actions">
          <button onClick={() => run(regenerate.mutateAsync())}>Regenerate</button>
          <button onClick={() => window.print()}>Print</button>
          <button
            className="primary"
            disabled={list.finalized_at != null}
            onClick={() => run(finish.mutateAsync())}
          >
            {list.finalized_at ? 'Shopping done' : 'Done shopping'}
          </button>
        </div>
      </div>

      <h1 className="print-only">Shopping list — {formatWeek(list.week_start)}</h1>

      {groupByCategory(buy).map((group) => (
        <div key={group.label} className="aisle">
          <h2>{group.label}</h2>
          <ul className="items">
            {group.items.map((item) => (
              <li key={item.id} className={item.checked ? 'item item--checked' : 'item'}>
                <label>
                  <input
                    type="checkbox"
                    checked={item.checked}
                    onChange={(e) =>
                      run(check.mutateAsync({ itemId: item.id, checked: e.target.checked }))
                    }
                  />
                  <span className="item__amount">{amountOf(item)}</span>
                  <span className="item__name" title={why(item)}>
                    {item.name}
                  </span>
                  {item.source !== 'recipe' && <span className="muted no-print"> (added)</span>}
                </label>
                {item.source !== 'recipe' && (
                  <button className="link no-print" onClick={() => run(drop.mutateAsync(item.id))}>
                    remove
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}

      {buy.length === 0 && <p className="muted">Nothing to buy yet.</p>}

      {staples.length > 0 && (
        <div className="aisle">
          <h2>Check your seasonings</h2>
          <ul className="items">
            {staples.map((item) => (
              <li key={item.id} className="item">
                <label>
                  <input
                    type="checkbox"
                    checked={item.checked}
                    onChange={(e) =>
                      run(check.mutateAsync({ itemId: item.id, checked: e.target.checked }))
                    }
                  />
                  <span className="item__name">{item.name}</span>
                  <span className="muted">
                    {' '}
                    — {item.contributions.map((c) => c.recipe_name).join(', ')}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="no-print">
        <ManualAdd listId={list.id} planId={planId} />
        {suggestions.length > 0 && (
          <div className="suggestions">
            <span className="muted">You usually buy:</span>
            {suggestions.map((suggestion) => (
              <button
                key={`${suggestion.ingredient_id ?? suggestion.name}`}
                onClick={() =>
                  run(
                    accept.mutateAsync({
                      ingredientId: suggestion.ingredient_id,
                      name: suggestion.name,
                    }),
                  )
                }
              >
                + {suggestion.name}
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
