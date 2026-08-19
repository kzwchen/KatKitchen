import { describe, expect, it } from 'vitest'
import { formatWeek, mondayOf, slotIndex } from './weeks'

describe('mondayOf', () => {
  // A known week: Monday 2026-08-17 through Sunday 2026-08-23. Every day in
  // it, including Sunday, must resolve back to that same Monday. Sunday is
  // the case most likely to be got wrong: JS Date#getDay() returns 0 for
  // Sunday, not 7, so a naive (getDay() + 6) % 7 offset that forgot the
  // wraparound would treat Sunday as its own start-of-week instead of the
  // last day of the previous one.
  const WEEK: [string, number][] = [
    ['2026-08-17', 1], // Monday
    ['2026-08-18', 2], // Tuesday
    ['2026-08-19', 3], // Wednesday
    ['2026-08-20', 4], // Thursday
    ['2026-08-21', 5], // Friday
    ['2026-08-22', 6], // Saturday
    ['2026-08-23', 0], // Sunday
  ]

  it.each(WEEK)('resolves %s (getDay() === %i) to 2026-08-17', (isoDate, expectedGetDay) => {
    const [year, month, day] = isoDate.split('-').map(Number)
    const date = new Date(year, month - 1, day)
    expect(date.getDay()).toBe(expectedGetDay)
    expect(mondayOf(date)).toBe('2026-08-17')
  })

  it('resolves the following Monday to itself', () => {
    expect(mondayOf(new Date(2026, 7, 24))).toBe('2026-08-24')
  })

  it('crosses a month boundary correctly', () => {
    // 2026-03-01 is a Sunday; its Monday is in February.
    const sunday = new Date(2026, 2, 1)
    expect(sunday.getDay()).toBe(0)
    expect(mondayOf(sunday)).toBe('2026-02-23')
  })
})

describe('slotIndex', () => {
  it('orders slots within the same day as breakfast < lunch < dinner', () => {
    expect(slotIndex(0, 'breakfast')).toBeLessThan(slotIndex(0, 'lunch'))
    expect(slotIndex(0, 'lunch')).toBeLessThan(slotIndex(0, 'dinner'))
  })

  it('always ranks an earlier day before a later day, regardless of slot', () => {
    expect(slotIndex(0, 'dinner')).toBeLessThan(slotIndex(1, 'breakfast'))
    expect(slotIndex(1, 'dinner')).toBeLessThan(slotIndex(2, 'breakfast'))
  })

  it('gives every day/slot combination in a week a distinct index', () => {
    const slots: Array<'breakfast' | 'lunch' | 'dinner'> = ['breakfast', 'lunch', 'dinner']
    const indices = new Set<number>()
    for (let day = 0; day < 7; day++) {
      for (const slot of slots) {
        indices.add(slotIndex(day, slot))
      }
    }
    expect(indices.size).toBe(21)
  })
})

describe('formatWeek', () => {
  it('formats a known week_start as a short, human-readable date', () => {
    expect(formatWeek('2026-08-17')).toBe('Mon, Aug 17, 2026')
  })
})
