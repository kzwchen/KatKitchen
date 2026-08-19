import { useState } from 'react'
import { deleteIngredient, updateIngredient } from '../../api/client'
import { keys, useIngredients, useInvalidatingMutation } from '../../api/hooks'
import { useToast } from '../../components/Toast'
import { CATEGORY_LABELS, CATEGORY_ORDER } from '../../types'
import type { Category, Ingredient } from '../../types'
import { NewIngredientForm } from './NewIngredientForm'

export function IngredientsPage() {
  const [search, setSearch] = useState('')
  const { data: ingredients = [], isLoading } = useIngredients(search || undefined)
  const toast = useToast()

  const update = useInvalidatingMutation(
    ({ id, body }: { id: number; body: Parameters<typeof updateIngredient>[1] }) =>
      updateIngredient(id, body),
    [keys.ingredients(), keys.ingredients(search)],
  )
  const remove = useInvalidatingMutation(deleteIngredient, [
    keys.ingredients(),
    keys.ingredients(search),
  ])

  async function run(action: Promise<unknown>) {
    try {
      await action
    } catch (error) {
      toast.showError(error)
    }
  }

  return (
    <section>
      <h1>Ingredients</h1>
      <p className="muted">
        An ingredient's unit is fixed once a recipe uses it, so the shopping list can add
        amounts together without guessing.
      </p>

      <NewIngredientForm />

      <input
        className="search"
        placeholder="Search ingredients"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {isLoading ? (
        <p className="muted">Loading…</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Category</th>
              <th>Unit</th>
              <th>Staple</th>
              <th>Used by</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {ingredients.map((ingredient: Ingredient) => (
              <tr key={ingredient.id}>
                <td>{ingredient.name}</td>
                <td>
                  <select
                    value={ingredient.category}
                    onChange={(e) =>
                      run(
                        update.mutateAsync({
                          id: ingredient.id,
                          body: { category: e.target.value as Category },
                        }),
                      )
                    }
                  >
                    {CATEGORY_ORDER.map((c) => (
                      <option key={c} value={c}>
                        {CATEGORY_LABELS[c]}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  {ingredient.unit}
                  {ingredient.usage_count > 0 && (
                    <span className="muted" title="Locked because recipes use this unit">
                      {' '}
                      (locked)
                    </span>
                  )}
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={ingredient.is_staple}
                    onChange={(e) =>
                      run(
                        update.mutateAsync({
                          id: ingredient.id,
                          body: { is_staple: e.target.checked },
                        }),
                      )
                    }
                  />
                </td>
                <td className="muted">{ingredient.usage_count} recipes</td>
                <td>
                  <button
                    disabled={ingredient.usage_count > 0}
                    title={
                      ingredient.usage_count > 0
                        ? 'Used by a recipe — remove it there first'
                        : undefined
                    }
                    onClick={() => run(remove.mutateAsync(ingredient.id))}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
