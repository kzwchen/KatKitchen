import { useState } from 'react'
import type { Meal, MealKind, MealSlot, RecipeSummary } from '../../types'
import { slotIndex, slotLabel } from './weeks'

/** Cook meals of this recipe that happen strictly earlier in the week. */
export function leftoverOptions(
  recipeId: number,
  day: number,
  slot: MealSlot,
  meals: Meal[],
): Meal[] {
  const here = slotIndex(day, slot)
  return meals.filter(
    (meal) =>
      meal.kind === 'cook' &&
      meal.recipe_id === recipeId &&
      slotIndex(meal.day, meal.slot) < here,
  )
}

interface Props {
  day: number
  slot: MealSlot
  meals: Meal[]
  recipes: RecipeSummary[]
  onPick: (choice: { recipeId: number; kind: MealKind; sourceMealId: number | null }) => void
  onClose: () => void
}

export function SlotPicker({ day, slot, meals, recipes, onPick, onClose }: Props) {
  const [query, setQuery] = useState('')
  const trimmed = query.trim().toLowerCase()
  const matches = trimmed
    ? recipes.filter((recipe) => recipe.name.toLowerCase().includes(trimmed))
    : []

  return (
    <div className="slot-picker">
      <input
        autoFocus
        placeholder="Search recipes"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
      />
      <ul role="listbox">
        {matches.flatMap((recipe) => {
          // Leftovers come first: if the recipe is already cooked this week,
          // reusing that batch is almost always what you meant.
          const sources = leftoverOptions(recipe.id, day, slot, meals)
          return [
            ...sources.map((source) => (
              <li key={`leftover-${recipe.id}-${source.id}`}>
                <button
                  type="button"
                  role="option"
                  aria-selected={false}
                  onClick={() =>
                    onPick({ recipeId: recipe.id, kind: 'leftovers', sourceMealId: source.id })
                  }
                >
                  Leftovers of {slotLabel(source.day, source.slot)} ({recipe.name})
                </button>
              </li>
            )),
            <li key={`cook-${recipe.id}`}>
              <button
                type="button"
                role="option"
                aria-selected={false}
                onClick={() => onPick({ recipeId: recipe.id, kind: 'cook', sourceMealId: null })}
              >
                Cook {recipe.name} (serves {recipe.serves})
              </button>
            </li>,
          ]
        })}
      </ul>
    </div>
  )
}
