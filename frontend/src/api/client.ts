import type {
  CanonicalUnit,
  Category,
  Ingredient,
  ListItem,
  ListSummary,
  MealKind,
  MealSlot,
  Plan,
  PlanSummary,
  Recipe,
  RecipeLineInput,
  RecipeSummary,
  Settings,
  ShoppingList,
  Suggestion,
} from '../types'

/** Mirrors the backend's {detail, code} error contract. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (response.status === 204) return undefined as T
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(
      body.detail ?? `Request failed with status ${response.status}`,
      body.code ?? 'unknown',
      response.status,
    )
  }
  return (await response.json()) as T
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

function patch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

function remove(path: string): Promise<void> {
  return request<void>(path, { method: 'DELETE' })
}

function withQuery(path: string, q?: string): string {
  return q ? `${path}?q=${encodeURIComponent(q)}` : path
}

// Ingredients
export const getIngredients = (q?: string) =>
  request<Ingredient[]>(withQuery('/api/ingredients', q))
export const createIngredient = (body: {
  name: string
  category: Category
  unit: CanonicalUnit
  is_staple?: boolean
}) => post<Ingredient>('/api/ingredients', body)
export const updateIngredient = (
  id: number,
  body: Partial<{ name: string; category: Category; unit: CanonicalUnit; is_staple: boolean }>,
) => patch<Ingredient>(`/api/ingredients/${id}`, body)
export const deleteIngredient = (id: number) => remove(`/api/ingredients/${id}`)

// Recipes
export const getRecipes = (q?: string) => request<RecipeSummary[]>(withQuery('/api/recipes', q))
export const getRecipe = (id: number) => request<Recipe>(`/api/recipes/${id}`)
export const createRecipe = (body: {
  name: string
  serves: number
  instructions: string
  source_url?: string | null
  notes?: string | null
  lines: RecipeLineInput[]
}) => post<Recipe>('/api/recipes', body)
export const updateRecipe = (
  id: number,
  body: Partial<{
    name: string
    serves: number
    instructions: string
    source_url: string | null
    notes: string | null
    lines: RecipeLineInput[]
  }>,
) => patch<Recipe>(`/api/recipes/${id}`, body)
export const deleteRecipe = (id: number) => remove(`/api/recipes/${id}`)

// Plans and meals
export const getPlans = () => request<PlanSummary[]>('/api/plans')
export const getPlan = (id: number) => request<Plan>(`/api/plans/${id}`)
export const createPlan = (weekStart: string) => post<Plan>('/api/plans', { week_start: weekStart })
export const deletePlan = (id: number) => remove(`/api/plans/${id}`)
export const addMeal = (
  planId: number,
  body: {
    day: number
    slot: MealSlot
    recipe_id: number
    kind: MealKind
    servings_to_make?: number | null
    servings_eaten?: number | null
    source_meal_id?: number | null
  },
) => post(`/api/plans/${planId}/meals`, body)
export const updateMeal = (
  mealId: number,
  body: Partial<{ servings_to_make: number; servings_eaten: number }>,
) => patch(`/api/meals/${mealId}`, body)
export const deleteMeal = (mealId: number) => remove(`/api/meals/${mealId}`)

// Shopping lists
export const getList = (planId: number) => request<ShoppingList>(`/api/plans/${planId}/list`)
export const generateList = (planId: number) => post<ShoppingList>(`/api/plans/${planId}/list`)
export const addListItem = (
  listId: number,
  body: {
    custom_name?: string | null
    ingredient_id?: number | null
    quantity?: number | null
    display_unit?: string | null
    note?: string | null
  },
) => post<ListItem>(`/api/lists/${listId}/items`, body)
export const updateListItem = (
  listId: number,
  itemId: number,
  body: Partial<{ checked: boolean; quantity: number; display_unit: string; note: string }>,
) => patch<ListItem>(`/api/lists/${listId}/items/${itemId}`, body)
export const deleteListItem = (listId: number, itemId: number) =>
  remove(`/api/lists/${listId}/items/${itemId}`)
export const finalizeList = (listId: number) => post<ShoppingList>(`/api/lists/${listId}/finalize`)
export const getListHistory = () => request<ListSummary[]>('/api/lists')
export const getListById = (listId: number) => request<ShoppingList>(`/api/lists/${listId}`)
export const getSuggestions = (listId: number) =>
  request<Suggestion[]>(`/api/lists/${listId}/suggestions`)

// Settings
export const getSettings = () => request<Settings>('/api/settings')
export const updateSettings = (householdSize: number) =>
  patch<Settings>('/api/settings', { household_size: householdSize })
