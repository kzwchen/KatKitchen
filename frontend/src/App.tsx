import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { PlannerPage } from './pages/Planner/PlannerPage'

function Placeholder({ name }: { name: string }) {
  return <p>{name} lands in a later task.</p>
}

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/planner" replace />} />
        <Route path="planner" element={<PlannerPage />} />
        <Route path="planner/:planId" element={<PlannerPage />} />
        <Route path="recipes" element={<Placeholder name="Recipes" />} />
        <Route path="recipes/new" element={<Placeholder name="Recipe editor" />} />
        <Route path="recipes/:recipeId" element={<Placeholder name="Recipe editor" />} />
        <Route path="ingredients" element={<Placeholder name="Ingredients" />} />
        <Route path="list/:planId" element={<Placeholder name="Shopping list" />} />
        <Route path="history" element={<Placeholder name="History" />} />
        <Route path="history/:listId" element={<Placeholder name="Archived list" />} />
      </Route>
    </Routes>
  )
}
