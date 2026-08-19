import { useState } from 'react'
import { createIngredient } from '../../api/client'
import { keys, useInvalidatingMutation } from '../../api/hooks'
import { useToast } from '../../components/Toast'
import {
  CATEGORY_LABELS,
  CATEGORY_ORDER,
  DEFAULT_UNIT_FOR_CATEGORY,
} from '../../types'
import type { CanonicalUnit, Category, Ingredient } from '../../types'

const UNITS: { value: CanonicalUnit; label: string }[] = [
  { value: 'count', label: 'count (whole items)' },
  { value: 'g', label: 'grams (weight)' },
  { value: 'ml', label: 'millilitres (volume)' },
]

interface Props {
  initialName?: string
  onCreated?: (ingredient: Ingredient) => void
  onCancel?: () => void
}

export function NewIngredientForm({ initialName = '', onCreated, onCancel }: Props) {
  const [name, setName] = useState(initialName)
  const [category, setCategory] = useState<Category>('produce')
  const [unit, setUnit] = useState<CanonicalUnit>(DEFAULT_UNIT_FOR_CATEGORY.produce)
  const [unitTouched, setUnitTouched] = useState(false)
  const [isStaple, setIsStaple] = useState(false)
  const [stapleTouched, setStapleTouched] = useState(false)
  const toast = useToast()

  // Invalidate the one-element ['ingredients'] prefix, not keys.ingredients()
  // (which is ['ingredients', ''] -- the no-search variant only). TanStack
  // Query v5 exact-matches primitive key segments, so invalidating the exact
  // no-search key would miss an active ['ingredients', <search term>] query,
  // e.g. the Ingredients page while a search is typed. The one-element
  // prefix partial-matches every search variant.
  const create = useInvalidatingMutation(createIngredient, [['ingredients']])

  // The category drives the unit and staple defaults until the user overrides them.
  function pickCategory(next: Category) {
    setCategory(next)
    if (!unitTouched) setUnit(DEFAULT_UNIT_FOR_CATEGORY[next])
    if (!stapleTouched) setIsStaple(next === 'seasoning')
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    try {
      const ingredient = await create.mutateAsync({
        name: name.trim(),
        category,
        unit,
        is_staple: isStaple,
      })
      setName('')
      onCreated?.(ingredient)
    } catch (error) {
      toast.showError(error)
    }
  }

  return (
    <form className="ingredient-form" aria-label="New ingredient" onSubmit={submit}>
      <label>
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label>
        Category
        <select value={category} onChange={(e) => pickCategory(e.target.value as Category)}>
          {CATEGORY_ORDER.map((c) => (
            <option key={c} value={c}>
              {CATEGORY_LABELS[c]}
            </option>
          ))}
        </select>
      </label>
      <label>
        Unit
        <select
          value={unit}
          onChange={(e) => {
            setUnitTouched(true)
            setUnit(e.target.value as CanonicalUnit)
          }}
        >
          {UNITS.map((u) => (
            <option key={u.value} value={u.value}>
              {u.label}
            </option>
          ))}
        </select>
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={isStaple}
          onChange={(e) => {
            setStapleTouched(true)
            setIsStaple(e.target.checked)
          }}
        />
        Staple (reminder only, no quantity on the list)
      </label>
      <div className="ingredient-form__actions">
        <button className="primary" type="submit" disabled={create.isPending}>
          Add ingredient
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}
