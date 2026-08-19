import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { createRecipe, updateRecipe } from '../../api/client'
import { keys, useInvalidatingMutation, useRecipe } from '../../api/hooks'
import { useToast } from '../../components/Toast'
import { NewIngredientForm } from '../Ingredients/NewIngredientForm'
import { LineRow } from './LineRow'
import type { EditorLine } from './LineRow'
import type { Ingredient } from '../../types'

let nextKey = 0
const blankLine = (): EditorLine => ({
  key: `line-${nextKey++}`,
  ingredient: null,
  quantity: '',
  displayUnit: '',
  prepNote: '',
})

// Bumped every time a "Create <name>" is requested, so the inline form's `key`
// changes and React remounts it fresh — otherwise a second inline creation
// (from the same or a different line) reuses the first NewIngredientForm
// instance and inherits its stale category/unit/staple state.
let nextRequestId = 0

export function RecipeEditorPage() {
  const { recipeId } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const id = recipeId ? Number(recipeId) : undefined
  const { data: existing } = useRecipe(id)

  const [name, setName] = useState('')
  const [serves, setServes] = useState('2')
  const [instructions, setInstructions] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [lines, setLines] = useState<EditorLine[]>([])
  const [error, setError] = useState<string | null>(null)
  // Which line asked for a new ingredient, so the created one lands in it.
  const [creatingFor, setCreatingFor] = useState<{
    key: string
    name: string
    requestId: number
  } | null>(null)

  useEffect(() => {
    if (!existing) return
    setName(existing.name)
    setServes(String(existing.serves))
    setInstructions(existing.instructions)
    setSourceUrl(existing.source_url ?? '')
    setLines(
      existing.lines.map((line) => ({
        key: `line-${nextKey++}`,
        ingredient: {
          id: line.ingredient_id,
          name: line.ingredient_name,
          category: line.category,
          unit: line.ingredient_unit,
          is_staple: false,
          usage_count: 0,
        },
        quantity: String(line.display_quantity),
        displayUnit: line.display_unit,
        prepNote: line.prep_note ?? '',
      })),
    )
  }, [existing])

  const save = useInvalidatingMutation(
    (body: Parameters<typeof createRecipe>[0]) =>
      id ? updateRecipe(id, body) : createRecipe(body),
    [keys.recipes(), ...(id ? [keys.recipe(id)] : [])],
  )

  function updateLine(key: string, next: EditorLine) {
    setLines((current) => current.map((line) => (line.key === key ? next : line)))
  }

  function ingredientCreated(ingredient: Ingredient) {
    if (!creatingFor) return
    setLines((current) =>
      current.map((line) =>
        line.key === creatingFor.key
          ? { ...line, ingredient, displayUnit: ingredient.unit }
          : line,
      ),
    )
    setCreatingFor(null)
  }

  async function submit() {
    setError(null)
    if (lines.some((line) => !line.ingredient)) {
      setError('Pick an ingredient for every line, or remove the empty ones.')
      return
    }
    try {
      await save.mutateAsync({
        name: name.trim(),
        serves: Number(serves),
        instructions,
        source_url: sourceUrl.trim() || null,
        lines: lines.map((line) => ({
          ingredient_id: line.ingredient!.id,
          quantity: Number(line.quantity),
          display_unit: line.displayUnit,
          prep_note: line.prepNote.trim() || null,
        })),
      })
      navigate('/recipes')
    } catch (err) {
      toast.showError(err)
    }
  }

  return (
    <section>
      <h1>{id ? 'Edit recipe' : 'New recipe'}</h1>
      {/*
        Not a <form>: NewIngredientForm below renders its own real <form>,
        and nested <form> elements are invalid HTML — a real browser resolves
        a submit click inside the inner form to the OUTER form's native
        submission (a full page navigation), silently discarding all React
        state. "Save recipe" is a plain button with an onClick handler instead.
      */}
      <div className="recipe-form">
        <div className="recipe-form__head">
          <label>
            Recipe name
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Serves
            <input
              type="number"
              min="1"
              value={serves}
              onChange={(e) => setServes(e.target.value)}
              required
            />
          </label>
          <label>
            Source URL
            <input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} />
          </label>
        </div>

        <h2>Ingredients</h2>
        {lines.map((line) => (
          <LineRow
            key={line.key}
            line={line}
            onChange={(next) => updateLine(line.key, next)}
            onRemove={() => setLines((c) => c.filter((l) => l.key !== line.key))}
            onCreateRequest={(typedName) =>
              setCreatingFor({ key: line.key, name: typedName, requestId: nextRequestId++ })
            }
          />
        ))}
        <button type="button" onClick={() => setLines((c) => [...c, blankLine()])}>
          Add ingredient line
        </button>

        {creatingFor && (
          <div className="inline-create">
            <h3>New ingredient</h3>
            <NewIngredientForm
              key={creatingFor.requestId}
              initialName={creatingFor.name}
              onCreated={ingredientCreated}
              onCancel={() => setCreatingFor(null)}
            />
          </div>
        )}

        <label className="block">
          Instructions
          <textarea
            rows={10}
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
        </label>

        {error && <p className="error">{error}</p>}
        <div className="recipe-form__actions">
          <button className="primary" type="button" onClick={submit} disabled={save.isPending}>
            Save recipe
          </button>
          <button type="button" onClick={() => navigate('/recipes')}>
            Cancel
          </button>
        </div>
      </div>
    </section>
  )
}
