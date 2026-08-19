import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { updateSettings } from '../api/client'
import { keys, useInvalidatingMutation, useSettings } from '../api/hooks'
import { useToast } from './Toast'

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
  const toast = useToast()
  const [draft, setDraft] = useState(String(settings?.household_size ?? 2))

  useEffect(() => {
    setDraft(String(settings?.household_size ?? 2))
  }, [settings?.household_size])

  function commit() {
    const serverValue = String(settings?.household_size ?? 2)
    const parsed = Number(draft)
    // The API declares household_size as `int >= 1`, so a fraction is a
    // guaranteed 422. The field's `step="1"` stops most of them; this catches
    // the rest (pasted text, a browser that ignores the step).
    // isInteger covers NaN and Infinity too, so no isFinite check is needed.
    if (parsed < 1 || !Number.isInteger(parsed)) {
      setDraft(serverValue)
      return
    }
    if (parsed !== settings?.household_size) {
      save.mutateAsync(parsed).catch((error) => {
        toast.showError(error)
        // Nothing was saved, so leaving the rejected number on screen would
        // claim otherwise -- and the resync effect above cannot correct it,
        // since the server value never changed.
        setDraft(serverValue)
      })
    }
    // "04" parses to the value already on the server: no request goes out and
    // the resync effect never fires, so without this the field keeps showing
    // "04" until a reload.
    setDraft(String(parsed))
  }

  return (
    <label className="nav__setting">
      Household
      <input
        type="number"
        min="1"
        step="1"
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
        <span className="nav__brand">KatKitchen</span>
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
