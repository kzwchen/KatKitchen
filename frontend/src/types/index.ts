export type Category =
  | 'produce'
  | 'bakery'
  | 'meat_seafood'
  | 'dairy'
  | 'frozen'
  | 'dry_goods'
  | 'seasoning'
  | 'other'

export type CanonicalUnit = 'count' | 'g' | 'ml'
export type PlanStatus = 'planning' | 'shopping' | 'done'
export type MealSlot = 'breakfast' | 'lunch' | 'dinner'
export type MealKind = 'cook' | 'leftovers'
export type ItemSource = 'recipe' | 'manual' | 'suggested'
export type ItemSection = 'buy' | 'staple_check'

/** Store-walk order, matching the backend's CATEGORY_ORDER. */
export const CATEGORY_ORDER: Category[] = [
  'produce',
  'bakery',
  'meat_seafood',
  'dairy',
  'frozen',
  'dry_goods',
  'seasoning',
  'other',
]

export const CATEGORY_LABELS: Record<Category, string> = {
  produce: 'Produce',
  bakery: 'Bakery',
  meat_seafood: 'Meat & seafood',
  dairy: 'Dairy',
  frozen: 'Frozen',
  dry_goods: 'Dry goods',
  seasoning: 'Seasonings',
  other: 'Other',
}

/** Which entry units are legal for an ingredient, keyed by its canonical unit. */
export const UNIT_FAMILIES: Record<CanonicalUnit, string[]> = {
  count: ['count'],
  g: ['g', 'kg', 'oz', 'lb'],
  ml: ['ml', 'l', 'tsp', 'tbsp', 'cup'],
}

export const DEFAULT_UNIT_FOR_CATEGORY: Record<Category, CanonicalUnit> = {
  produce: 'count',
  bakery: 'count',
  meat_seafood: 'g',
  dairy: 'ml',
  frozen: 'g',
  dry_goods: 'g',
  seasoning: 'ml',
  other: 'count',
}

export const SLOTS: MealSlot[] = ['breakfast', 'lunch', 'dinner']
export const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export interface Ingredient {
  id: number
  name: string
  category: Category
  unit: CanonicalUnit
  is_staple: boolean
  usage_count: number
}

export interface RecipeLine {
  id: number
  ingredient_id: number
  ingredient_name: string
  ingredient_unit: CanonicalUnit
  category: Category
  quantity: number
  display_quantity: number
  display_unit: string
  prep_note: string | null
  position: number
}

export interface Recipe {
  id: number
  name: string
  serves: number
  instructions: string
  source_url: string | null
  notes: string | null
  lines: RecipeLine[]
}

export interface RecipeSummary {
  id: number
  name: string
  serves: number
  line_count: number
}

export interface RecipeLineInput {
  ingredient_id: number
  quantity: number
  display_unit: string
  prep_note?: string | null
}

export interface Meal {
  id: number
  day: number
  slot: MealSlot
  recipe_id: number
  recipe_name: string
  recipe_serves: number
  kind: MealKind
  servings_to_make: number | null
  servings_eaten: number
  source_meal_id: number | null
}

export interface SlotWarning {
  meal_id: number
  message: string
}

export interface Plan {
  id: number
  week_start: string
  status: PlanStatus
  meals: Meal[]
  warnings: SlotWarning[]
}

export interface PlanSummary {
  id: number
  week_start: string
  status: PlanStatus
  meal_count: number
  has_list: boolean
}

export interface Contribution {
  recipe_id: number
  recipe_name: string
  quantity: number
}

export interface ListItem {
  id: number
  ingredient_id: number | null
  name: string
  category: Category | null
  quantity: number | null
  display_quantity: number | null
  display_unit: string | null
  source: ItemSource
  section: ItemSection
  checked: boolean
  note: string | null
  contributions: Contribution[]
}

export interface ShoppingList {
  id: number
  plan_id: number
  week_start: string
  generated_at: string
  finalized_at: string | null
  items: ListItem[]
}

export interface ListSummary {
  id: number
  plan_id: number
  week_start: string
  finalized_at: string | null
  item_count: number
  checked_count: number
}

export interface Suggestion {
  ingredient_id: number | null
  name: string
  times_bought: number
}

export interface Settings {
  household_size: number
}
