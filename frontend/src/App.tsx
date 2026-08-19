import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { IngredientsPage } from './pages/Ingredients/IngredientsPage'
import { RecipesPage } from './pages/Recipes/RecipesPage'
import { RecipeEditorPage } from './pages/RecipeEditor/RecipeEditorPage'

function Placeholder({ name }: { name: string }) {
  return <p>{name} lands in a later task.</p>
}

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/planner" replace />} />
        <Route path="planner" element={<Placeholder name="Planner" />} />
        <Route path="planner/:planId" element={<Placeholder name="Planner" />} />
        <Route path="recipes" element={<RecipesPage />} />
        <Route path="recipes/new" element={<RecipeEditorPage />} />
        <Route path="recipes/:recipeId" element={<RecipeEditorPage />} />
        <Route path="ingredients" element={<IngredientsPage />} />
        <Route path="list/:planId" element={<Placeholder name="Shopping list" />} />
        <Route path="history" element={<Placeholder name="History" />} />
        <Route path="history/:listId" element={<Placeholder name="Archived list" />} />
      </Route>
    </Routes>
  )
}
