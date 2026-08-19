import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { IngredientsPage } from './pages/Ingredients/IngredientsPage'
import { RecipesPage } from './pages/Recipes/RecipesPage'
import { RecipeEditorPage } from './pages/RecipeEditor/RecipeEditorPage'
import { PlannerPage } from './pages/Planner/PlannerPage'
import { ShoppingListPage } from './pages/ShoppingList/ShoppingListPage'
import { HistoryPage } from './pages/History/HistoryPage'
import { ArchivedListPage } from './pages/History/ArchivedListPage'

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/planner" replace />} />
        <Route path="planner" element={<PlannerPage />} />
        <Route path="planner/:planId" element={<PlannerPage />} />
        <Route path="recipes" element={<RecipesPage />} />
        <Route path="recipes/new" element={<RecipeEditorPage />} />
        <Route path="recipes/:recipeId" element={<RecipeEditorPage />} />
        <Route path="ingredients" element={<IngredientsPage />} />
        <Route path="list/:planId" element={<ShoppingListPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="history/:listId" element={<ArchivedListPage />} />
      </Route>
    </Routes>
  )
}
