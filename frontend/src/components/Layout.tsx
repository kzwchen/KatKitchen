import { NavLink, Outlet } from 'react-router-dom'

const LINKS = [
  { to: '/planner', label: 'Planner' },
  { to: '/recipes', label: 'Recipes' },
  { to: '/ingredients', label: 'Ingredients' },
  { to: '/history', label: 'History' },
]

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
      </nav>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
