import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { updateSettings } from '../api/client'
import { keys, useInvalidatingMutation, useSettings } from '../api/hooks'

const LINKS = [
  { to: '/planner', label: 'Planner' },
  { to: '/recipes', label: 'Recipes' },
  { to: '/ingredients', label: 'Ingredients' },
  { to: '/history', label: 'History' },
]

/**
 * The household-size field, buffered in local state.
 *
 * Binding `value` straight to `settings?.household_size` has the same
 * failure mode the Planner's servings input had to work around: firing a
 * mutation on every keystroke flips `isPending` synchronously, which
 * re-renders with the stale cached value before the round trip completes
 * and snaps the field back mid-type. Instead the draft lives here and only
 * commits to the server on blur or Enter.
 */
function HouseholdSizeInput() {
  const { data: settings } = useSettings()
  const save = useInvalidatingMutation(updateSettings, [keys.settings()])
  const [draft, setDraft] = useState(String(settings?.household_size ?? 2))

  useEffect(() => {
    setDraft(String(settings?.household_size ?? 2))
  }, [settings?.household_size])

  function commit() {
    const parsed = Number(draft)
    if (!Number.isFinite(parsed) || parsed < 1) {
      setDraft(String(settings?.household_size ?? 2))
      return
    }
    if (parsed !== settings?.household_size) {
      save.mutate(parsed)
    }
  }

  return (
    <label className="nav__setting">
      Household
      <input
        type="number"
        min="1"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            commit()
          }
        }}
      />
    </label>
  )
}

export function Layout() {
  return (
    <div className="layout">
      <nav className="nav">
        <span className="nav__brand">RatKitchen</span>
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) => (isActive ? 'nav__link nav__link--active' : 'nav__link')}
          >
            {link.label}
          </NavLink>
        ))}
        <HouseholdSizeInput />
      </nav>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
