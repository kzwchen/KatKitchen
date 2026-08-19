import { DAY_NAMES, SLOTS } from '../../types'
import type { MealSlot } from '../../types'

/** The Monday of the week containing `date`, as YYYY-MM-DD. */
export function mondayOf(date: Date): string {
  const copy = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const offset = (copy.getDay() + 6) % 7 // Sunday is 0, so shift to Monday-first
  copy.setDate(copy.getDate() - offset)
  const month = String(copy.getMonth() + 1).padStart(2, '0')
  const day = String(copy.getDate()).padStart(2, '0')
  return `${copy.getFullYear()}-${month}-${day}`
}

export function formatWeek(weekStart: string): string {
  const [year, month, day] = weekStart.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

/** A single comparable position in the week, mirroring the backend. */
export function slotIndex(day: number, slot: MealSlot): number {
  return day * SLOTS.length + SLOTS.indexOf(slot)
}

export function slotLabel(day: number, slot: MealSlot): string {
  return `${DAY_NAMES[day]} ${slot}`
}
