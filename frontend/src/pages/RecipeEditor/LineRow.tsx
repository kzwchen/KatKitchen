import { IngredientPicker } from '../../components/IngredientPicker'
import { UNIT_FAMILIES } from '../../types'
import type { Ingredient } from '../../types'

export interface EditorLine {
  key: string
  ingredient: Ingredient | null
  quantity: string
  displayUnit: string
  prepNote: string
}

interface Props {
  line: EditorLine
  onChange: (line: EditorLine) => void
  onRemove: () => void
  onCreateRequest: (typedName: string) => void
}

export function LineRow({ line, onChange, onRemove, onCreateRequest }: Props) {
  const units = line.ingredient ? UNIT_FAMILIES[line.ingredient.unit] : []
  const name = line.ingredient?.name ?? 'ingredient'

  return (
    <div className="line-row">
      <IngredientPicker
        value={line.ingredient}
        onSelect={(ingredient) =>
          onChange({
            ...line,
            ingredient,
            // A fresh selection resets the unit to the ingredient's canonical one.
            displayUnit: ingredient ? ingredient.unit : '',
          })
        }
        onCreateRequest={onCreateRequest}
      />

      {line.ingredient && (
        <>
          <input
            type="number"
            min="0"
            step="any"
            aria-label={`Quantity for ${name}`}
            value={line.quantity}
            onChange={(e) => onChange({ ...line, quantity: e.target.value })}
          />
          {units.length > 1 ? (
            <select
              aria-label={`Unit for ${name}`}
              value={line.displayUnit}
              onChange={(e) => onChange({ ...line, displayUnit: e.target.value })}
            >
              {units.map((unit) => (
                <option key={unit} value={unit}>
                  {unit}
                </option>
              ))}
            </select>
          ) : (
            <span className="muted">whole</span>
          )}
          <input
            aria-label={`Prep note for ${name}`}
            placeholder="diced, boneless…"
            value={line.prepNote}
            onChange={(e) => onChange({ ...line, prepNote: e.target.value })}
          />
        </>
      )}

      <button type="button" onClick={onRemove} aria-label={`Remove ${name}`}>
        ×
      </button>
    </div>
  )
}
