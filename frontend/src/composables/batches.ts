// Batches (stock entries) of one product: the order Steward uses them in, and a short label to pick one.
import { t } from '@/i18n'
import { formatAmount, formatDate } from './format'
import type { Location, StockEntry } from '@/types'

/** Same order as the server: opened first, then the one that expires first, then the oldest purchase. */
export function sortBatches(entries: StockEntry[]): StockEntry[] {
  return [...entries].sort(
    (a, b) =>
      Number(!a.opened_at) - Number(!b.opened_at) ||
      (a.due_date ?? '9999').localeCompare(b.due_date ?? '9999') ||
      a.purchased_at.localeCompare(b.purchased_at),
  )
}

/** Whether there is a real choice: more than one batch that differ in date, place or opened state. */
export function hasBatchChoice(entries: StockEntry[]): boolean {
  const keys = new Set(entries.map((e) => `${e.due_date}|${e.location_id}|${!!e.opened_at}`))
  return keys.size > 1
}

/** "03.11. · opened · Pantry · 1 pc" */
export function batchLabel(e: StockEntry, unit: string, locations: Map<number, Location>): string {
  const parts = [e.due_date ? formatDate(e.due_date) : t.rel.noDue]
  if (e.opened_at) parts.push(t.status.opened)
  if (e.location_id != null && locations.get(e.location_id)) parts.push(locations.get(e.location_id)!.name)
  parts.push(formatAmount(e.amount, unit))
  return parts.join(' · ')
}
