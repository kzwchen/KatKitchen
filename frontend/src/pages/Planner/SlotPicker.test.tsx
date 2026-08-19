import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SlotPicker, leftoverOptions } from './SlotPicker'
import type { Meal, RecipeSummary } from '../../types'

const RECIPES: RecipeSummary[] = [
  { id: 10, name: 'Chili', serves: 4, line_count: 3 },
  { id: 11, name: 'Soup', serves: 2, line_count: 2 },
]

const MONDAY_CHILI: Meal = {
  id: 1,
  day: 0,
  slot: 'dinner',
  recipe_id: 10,
  recipe_name: 'Chili',
  recipe_serves: 4,
  kind: 'cook',
  servings_to_make: 4,
  servings_eaten: 2,
  source_meal_id: null,
}

describe('leftoverOptions', () => {
  it('offers an earlier cook of the same recipe', () => {
    expect(leftoverOptions(10, 1, 'lunch', [MONDAY_CHILI])).toEqual([MONDAY_CHILI])
  })

  it('offers nothing for a slot before the cook', () => {
    expect(leftoverOptions(10, 0, 'lunch', [MONDAY_CHILI])).toEqual([])
  })

  it('offers nothing for a different recipe', () => {
    expect(leftoverOptions(11, 1, 'lunch', [MONDAY_CHILI])).toEqual([])
  })

  it('never offers a leftovers meal as a source', () => {
    const leftover: Meal = {
      ...MONDAY_CHILI,
      id: 2,
      day: 1,
      slot: 'lunch',
      kind: 'leftovers',
      servings_to_make: null,
      source_meal_id: 1,
    }
    expect(leftoverOptions(10, 2, 'lunch', [MONDAY_CHILI, leftover])).toEqual([MONDAY_CHILI])
  })
})

describe('SlotPicker', () => {
  function renderPicker(day: number, meals: Meal[], onPick = vi.fn()) {
    render(
      <SlotPicker
        day={day}
        slot="lunch"
        meals={meals}
        recipes={RECIPES}
        onPick={onPick}
        onClose={vi.fn()}
      />,
    )
    return onPick
  }

  it('lists leftovers first when the recipe is already cooked earlier', async () => {
    const user = userEvent.setup()
    renderPicker(1, [MONDAY_CHILI])
    await user.type(screen.getByPlaceholderText(/search recipes/i), 'chili')

    const options = screen.getAllByRole('option').map((o) => o.textContent)
    expect(options[0]).toMatch(/leftovers of mon dinner/i)
    expect(options[1]).toMatch(/cook chili/i)
  })

  it('reports a leftovers choice with its source meal', async () => {
    const user = userEvent.setup()
    const onPick = renderPicker(1, [MONDAY_CHILI])
    await user.type(screen.getByPlaceholderText(/search recipes/i), 'chili')
    await user.click(screen.getByRole('option', { name: /leftovers of mon dinner/i }))

    expect(onPick).toHaveBeenCalledWith({ recipeId: 10, kind: 'leftovers', sourceMealId: 1 })
  })

  it('reports a cook choice with no source', async () => {
    const user = userEvent.setup()
    const onPick = renderPicker(1, [MONDAY_CHILI])
    await user.type(screen.getByPlaceholderText(/search recipes/i), 'soup')
    await user.click(screen.getByRole('option', { name: /cook soup/i }))

    expect(onPick).toHaveBeenCalledWith({ recipeId: 11, kind: 'cook', sourceMealId: null })
  })

  it('offers only cooking when nothing is planned yet', async () => {
    const user = userEvent.setup()
    renderPicker(1, [])
    await user.type(screen.getByPlaceholderText(/search recipes/i), 'chili')

    const options = screen.getAllByRole('option').map((o) => o.textContent)
    expect(options).toEqual(['Cook Chili (serves 4)'])
  })
})
