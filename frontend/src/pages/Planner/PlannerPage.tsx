import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { addMeal, createPlan, deleteMeal, generateList, updateMeal } from '../../api/client'
import { keys, useInvalidatingMutation, usePlan, usePlans, useRecipes } from '../../api/hooks'
import { useToast } from '../../components/Toast'
import { DAY_NAMES, SLOTS } from '../../types'
import type { Meal, MealSlot } from '../../types'
import { SlotPicker } from './SlotPicker'
import { formatWeek, mondayOf } from './weeks'

interface ServingsInputProps {
  meal: Meal
  label: string
  onCommit: (servingsToMake: number) => void
}

/**
 * A batch-size field for a cook meal.
 *
 * This buffers the typed digits in local state rather than binding `value`
 * straight to `meal.servings_to_make`: firing a mutation on every keystroke
 * made `mutateAsync` flip `isPending` synchronously, re-rendering before the
 * network round trip and snapping the input back to the pre-edit digits, and
 * sent one PATCH per keystroke (so typing "10" could land as "1" or "0"
 * depending on response order). The value only commits to the server on
 * blur or Enter, and only if it parses to a finite number >= 1 -- a
 * transient empty field (which would otherwise serialise `NaN` to `null`
 * and blank the batch size) is silently reverted to the last known-good
 * value instead of sent.
 */
function ServingsInput({ meal, label, onCommit }: ServingsInputProps) {
  const [draft, setDraft] = useState(String(meal.servings_to_make ?? 1))

  // Keep the field in sync when the server value legitimately changes from
  // elsewhere (e.g. a refetch after another edit), but only while the user
  // isn't actively mid-edit-and-blurred-away from it -- there's no pending
  // local edit to preserve once this effect re-runs, since committing
  // always follows blur/Enter, not this prop change.
  useEffect(() => {
    setDraft(String(meal.servings_to_make ?? 1))
  }, [meal.servings_to_make])

  function commit() {
    const parsed = Number(draft)
    if (!Number.isFinite(parsed) || parsed < 1) {
      setDraft(String(meal.servings_to_make ?? 1))
      return
    }
    if (parsed !== meal.servings_to_make) {
      onCommit(parsed)
    }
  }

  return (
    <input
      type="number"
      min="1"
      value={draft}
      aria-label={label}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          commit()
        }
      }}
    />
  )
}

export function PlannerPage() {
  const { planId } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { data: plans = [] } = usePlans()
  const id = planId ? Number(planId) : plans[0]?.id
  const { data: plan } = usePlan(id)
  const { data: recipes = [] } = useRecipes()
  const [openSlot, setOpenSlot] = useState<{ day: number; slot: MealSlot } | null>(null)

  const invalidate = [keys.plans(), ...(id ? [keys.plan(id), keys.list(id)] : [])]
  const newPlan = useInvalidatingMutation(createPlan, [keys.plans()])
  const placeMeal = useInvalidatingMutation(
    (args: { planId: number; body: Parameters<typeof addMeal>[1] }) =>
      addMeal(args.planId, args.body),
    invalidate,
  )
  const editMeal = useInvalidatingMutation(
    (args: { mealId: number; body: Parameters<typeof updateMeal>[1] }) =>
      updateMeal(args.mealId, args.body),
    invalidate,
  )
  const removeMeal = useInvalidatingMutation(deleteMeal, invalidate)
  const makeList = useInvalidatingMutation(generateList, invalidate)

  async function run(action: Promise<unknown>) {
    try {
      await action
    } catch (error) {
      toast.showError(error)
    }
  }

  if (!plan) {
    return (
      <section>
        <h1>Planner</h1>
        <p className="muted">No week planned yet.</p>
        <button
          className="primary"
          onClick={() =>
            run(
              newPlan
                .mutateAsync(mondayOf(new Date()))
                .then((created) => navigate(`/planner/${created.id}`)),
            )
          }
        >
          Start this week
        </button>
      </section>
    )
  }

  const mealsAt = (day: number, slot: MealSlot): Meal[] =>
    plan.meals.filter((meal) => meal.day === day && meal.slot === slot)
  const warningFor = (mealId: number) => plan.warnings.find((w) => w.meal_id === mealId)

  return (
    <section>
      <div className="page-head">
        <h1>Week of {formatWeek(plan.week_start)}</h1>
        <div className="page-head__actions">
          <select
            value={plan.id}
            onChange={(e) => navigate(`/planner/${e.target.value}`)}
            aria-label="Choose a week"
          >
            {plans.map((p) => (
              <option key={p.id} value={p.id}>
                {formatWeek(p.week_start)}
              </option>
            ))}
          </select>
          <button
            onClick={() =>
              run(
                newPlan
                  .mutateAsync(mondayOf(new Date(Date.now() + 7 * 86400000)))
                  .then((created) => navigate(`/planner/${created.id}`)),
              )
            }
          >
            New week
          </button>
          <button
            className="primary"
            onClick={() => run(makeList.mutateAsync(plan.id).then(() => navigate(`/list/${plan.id}`)))}
          >
            Generate shopping list
          </button>
        </div>
      </div>

      <table className="grid">
        <thead>
          <tr>
            <th />
            {DAY_NAMES.map((day) => (
              <th key={day}>{day}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {SLOTS.map((slot) => (
            <tr key={slot}>
              <th scope="row">{slot}</th>
              {DAY_NAMES.map((_, day) => {
                const meals = mealsAt(day, slot)
                const isOpen = openSlot?.day === day && openSlot.slot === slot
                return (
                  <td key={day} className="grid__cell">
                    {meals.length > 0 && (
                      <div className="grid__meals">
                        {meals.map((meal) => (
                          <div key={meal.id} className={`meal meal--${meal.kind}`}>
                            <strong>{meal.recipe_name}</strong>
                            {meal.kind === 'cook' ? (
                              <label className="meal__servings">
                                makes
                                <ServingsInput
                                  meal={meal}
                                  label={`Servings for ${meal.recipe_name} on ${DAY_NAMES[day]} ${slot}`}
                                  onCommit={(servingsToMake) =>
                                    run(
                                      editMeal.mutateAsync({
                                        mealId: meal.id,
                                        body: { servings_to_make: servingsToMake },
                                      }),
                                    )
                                  }
                                />
                              </label>
                            ) : (
                              <span className="muted">leftovers</span>
                            )}
                            {warningFor(meal.id) && (
                              <span className="badge--warn" title={warningFor(meal.id)!.message}>
                                ⚠ short
                              </span>
                            )}
                            <button
                              className="link"
                              onClick={() => run(removeMeal.mutateAsync(meal.id))}
                            >
                              remove
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                    {isOpen ? (
                      <SlotPicker
                        day={day}
                        slot={slot}
                        meals={plan.meals}
                        recipes={recipes}
                        onClose={() => setOpenSlot(null)}
                        onPick={(choice) => {
                          setOpenSlot(null)
                          run(
                            placeMeal.mutateAsync({
                              planId: plan.id,
                              body: {
                                day,
                                slot,
                                recipe_id: choice.recipeId,
                                kind: choice.kind,
                                source_meal_id: choice.sourceMealId,
                              },
                            }),
                          )
                        }}
                      />
                    ) : (
                      <button
                        className="grid__add"
                        aria-label={`Add recipe to ${DAY_NAMES[day]} ${slot}`}
                        onClick={() => setOpenSlot({ day, slot })}
                      >
                        +
                      </button>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>

      {plan.warnings.length > 0 && (
        <ul className="warnings">
          {plan.warnings.map((warning) => (
            <li key={warning.meal_id} className="badge--warn">
              {warning.message}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
