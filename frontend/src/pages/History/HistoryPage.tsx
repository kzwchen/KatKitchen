import { Link } from 'react-router-dom'
import { useListHistory } from '../../api/hooks'
import { formatWeek } from '../Planner/weeks'

export function HistoryPage() {
  const { data: history = [], isLoading } = useListHistory()

  if (isLoading) return <p className="muted">Loading…</p>

  return (
    <section>
      <h1>Past weeks</h1>
      {history.length === 0 ? (
        <p className="muted">
          Nothing here yet. A week lands here once you mark its list "Done shopping".
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Week</th>
              <th>Bought</th>
              <th>Skipped</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {history.map((entry) => (
              <tr key={entry.id}>
                <td>{formatWeek(entry.week_start)}</td>
                <td>{entry.checked_count}</td>
                <td>{entry.item_count - entry.checked_count}</td>
                <td>
                  <Link to={`/history/${entry.id}`}>View list</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
