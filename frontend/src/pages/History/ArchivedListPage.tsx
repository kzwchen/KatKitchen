import { Link, useParams } from 'react-router-dom'
import { useListById } from '../../api/hooks'
import { groupByCategory } from '../ShoppingList/ShoppingListPage'
import { formatWeek } from '../Planner/weeks'

export function ArchivedListPage() {
  const listId = Number(useParams().listId)
  const { data: list, isLoading } = useListById(listId)

  if (isLoading) return <p className="muted">Loading…</p>
  if (!list) return <p className="muted">No such list.</p>

  const buy = list.items.filter((item) => item.section === 'buy')

  return (
    <section className="shopping">
      <div className="page-head no-print">
        <h1>{formatWeek(list.week_start)}</h1>
        <Link to="/history">Back to history</Link>
      </div>

      {groupByCategory(buy).map((group) => (
        <div key={group.label} className="aisle">
          <h2>{group.label}</h2>
          <ul className="items">
            {group.items.map((item) => (
              <li key={item.id} className={item.checked ? 'item item--checked' : 'item'}>
                <span className="item__amount">
                  {item.display_quantity != null
                    ? item.display_unit === 'count'
                      ? `${item.display_quantity} ×`
                      : `${item.display_quantity} ${item.display_unit}`
                    : ''}
                </span>
                <span className="item__name">{item.name}</span>
                <span className="muted">{item.checked ? 'bought' : 'skipped'}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  )
}
