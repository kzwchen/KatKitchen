import { useState } from 'react'
import { useIngredients } from '../api/hooks'
import type { Ingredient } from '../types'

interface Props {
  value: Ingredient | null
  /** null clears the current choice and reopens the search. */
  onSelect: (ingredient: Ingredient | null) => void
  onCreateRequest: (typedName: string) => void
}

export function IngredientPicker({ value, onSelect, onCreateRequest }: Props) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const { data: ingredients = [] } = useIngredients()

  if (value) {
    return (
      <span className="picker__chosen">
        {value.name}
        <button
          type="button"
          className="link"
          onClick={() => {
            setQuery('')
            setOpen(true)
            onSelect(null)
          }}
        >
          change
        </button>
      </span>
    )
  }

  const trimmed = query.trim()
  const matches = trimmed
    ? ingredients.filter((i) => i.name.toLowerCase().includes(trimmed.toLowerCase()))
    : ingredients
  const exact = matches.some((i) => i.name.toLowerCase() === trimmed.toLowerCase())

  return (
    <div className="picker">
      <input
        placeholder="Search ingredients"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
      />
      {open && (
        <ul className="picker__menu" role="listbox">
          {matches.slice(0, 8).map((ingredient) => (
            <li key={ingredient.id}>
              <button
                type="button"
                role="option"
                aria-selected={false}
                onClick={() => {
                  onSelect(ingredient)
                  setOpen(false)
                }}
              >
                {ingredient.name}
                <span className="muted"> · {ingredient.unit}</span>
              </button>
            </li>
          ))}
          {trimmed && !exact && (
            <li>
              <button
                type="button"
                role="option"
                aria-selected={false}
                onClick={() => {
                  onCreateRequest(trimmed)
                  setOpen(false)
                }}
              >
                Create "{trimmed}"
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
