import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { addMeal, createPlan, deleteMeal, generateList, updateMeal } from '../../api/client'
import { keys, useInvalidatingMutation, usePlan, usePlans, useRecipes } from '../../api/hooks'
import { useToast } from '../../components/Toast'
import { DAY_NAMES, SLOTS } from '../../types'
import type { Meal, MealSlot } from '../../types'
import { SlotPicker } from './SlotPicker'
import { formatWeek, mondayOf } from './weeks'

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

  const mealAt = (day: number, slot: MealSlot): Meal | undefined =>
    plan.meals.find((meal) => meal.day === day && meal.slot === slot)
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
                const meal = mealAt(day, slot)
                const isOpen = openSlot?.day === day && openSlot.slot === slot
                return (
                  <td key={day} className="grid__cell">
                    {meal ? (
                      <div className={`meal meal--${meal.kind}`}>
                        <strong>{meal.recipe_name}</strong>
                        {meal.kind === 'cook' ? (
                          <label className="meal__servings">
                            makes
                            <input
                              type="number"
                              min="1"
                              value={meal.servings_to_make ?? 1}
                              aria-label={`Servings for ${meal.recipe_name} on ${DAY_NAMES[day]} ${slot}`}
                              onChange={(e) =>
                                run(
                                  editMeal.mutateAsync({
                                    mealId: meal.id,
                                    body: { servings_to_make: Number(e.target.value) },
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
                    ) : isOpen ? (
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
                      <button className="grid__add" onClick={() => setOpenSlot({ day, slot })}>
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
