import { Link, useParams } from 'react-router-dom'
import { useListById } from '../../api/hooks'
import { amountOf, groupByCategory } from '../ShoppingList/ShoppingListPage'
import { formatWeek } from '../Planner/weeks'

export function ArchivedListPage() {
  const listId = Number(useParams().listId)
  const { data: list, isLoading } = useListById(listId)

  if (isLoading) return <p className="muted">Loading…</p>
  if (!list) return <p className="muted">No such list.</p>

  const buy = list.items.filter((item) => item.section === 'buy')
  const staples = list.items.filter((item) => item.section === 'staple_check')

  return (
    <section className="shopping">
      <div className="page-head no-print">
        <h1>{formatWeek(list.week_start)}</h1>
        <Link to="/history">Back to history</Link>
      </div>

      {/* print.css hides `.page-head.no-print`, so the paper copy needs its
       * own heading -- same trick as ShoppingListPage. */}
      <h1 className="print-only">{formatWeek(list.week_start)}</h1>

      {groupByCategory(buy).map((group) => (
        <div key={group.label} className="aisle">
          <h2>{group.label}</h2>
          <ul className="items">
            {group.items.map((item) => (
              <li key={item.id} className={item.checked ? 'item item--checked' : 'item'}>
                <span className="item__amount">{amountOf(item)}</span>
                <span className="item__name">{item.name}</span>
                <span className="muted">{item.checked ? 'bought' : 'skipped'}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}

      {buy.length === 0 && <p className="muted">Nothing to buy yet.</p>}

      {/* The history row counts every item in the list, staples included, so
       * these have to appear or the summary promises rows this page cannot
       * show. Mirrors the live list's seasonings section without the
       * checkbox: an archived week is a record, not a worksheet. */}
      {staples.length > 0 && (
        <div className="aisle">
          <h2>Check your seasonings</h2>
          <ul className="items">
            {staples.map((item) => (
              <li key={item.id} className={item.checked ? 'item item--checked' : 'item'}>
                <span className="item__name">{item.name}</span>
                <span className="muted">
                  {' '}
                  — {item.contributions.map((c) => c.recipe_name).join(', ')}
                </span>
                <span className="muted">{item.checked ? 'bought' : 'skipped'}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
