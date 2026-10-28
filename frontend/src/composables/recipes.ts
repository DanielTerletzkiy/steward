// Recipe helpers: ingredient status colors and the "mark a meal as eaten" flow.
import { api } from '@/api'
import { t } from '@/i18n'
import { attempt, notify } from './notify'
import type { MealPlanEntry, MealSlot } from '@/types'

export const SLOTS: MealSlot[] = ['breakfast', 'lunch', 'dinner', 'snack']

export const statusColor: Record<string, string | undefined> = {
  have: 'success',
  partial: 'warning',
  missing: 'error',
  unlinked: undefined,
  optional: undefined,
}
export const statusIcon: Record<string, string> = {
  have: 'mdi-check-circle-outline',
  partial: 'mdi-circle-half-full',
  missing: 'mdi-close-circle-outline',
  unlinked: 'mdi-link-variant-off',
  optional: 'mdi-help-circle-outline',
}

/** Mark a meal as eaten; with `cook`, its ingredients leave stock. */
export async function completeMeal(entry: MealPlanEntry, cook: boolean) {
  const res = await attempt(() => api.mealDone(entry.id, cook))
  if (res) notify(t.mealplan.doneMsg)
  return !!res
}
