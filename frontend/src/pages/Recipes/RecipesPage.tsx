import { useState } from 'react'
import { Link } from 'react-router-dom'
import { deleteRecipe } from '../../api/client'
import { keys, useInvalidatingMutation, useRecipes } from '../../api/hooks'
import { useToast } from '../../components/Toast'

export function RecipesPage() {
  const [search, setSearch] = useState('')
  const { data: recipes = [], isLoading } = useRecipes(search || undefined)
  const toast = useToast()
  const remove = useInvalidatingMutation(deleteRecipe, [keys.recipes(), keys.recipes(search)])

  return (
    <section>
      <div className="page-head">
        <h1>Recipes</h1>
        <Link className="button primary" to="/recipes/new">
          New recipe
        </Link>
      </div>

      <input
        className="search"
        placeholder="Search recipes"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {isLoading ? (
        <p className="muted">Loading…</p>
      ) : recipes.length === 0 ? (
        <p className="muted">No recipes yet. Add one to start planning a week.</p>
      ) : (
        <ul className="cards">
          {recipes.map((recipe) => (
            <li key={recipe.id} className="card">
              <Link to={`/recipes/${recipe.id}`}>
                <strong>{recipe.name}</strong>
              </Link>
              <span className="muted">
                Serves {recipe.serves} · {recipe.line_count} ingredients
              </span>
              <button
                onClick={async () => {
                  try {
                    await remove.mutateAsync(recipe.id)
                  } catch (error) {
                    toast.showError(error)
                  }
                }}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
