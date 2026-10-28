// Appliances linked to Home Assistant: readable states, commands and the live chip.
import { t } from '@/i18n'
import type { ApplianceKind, Equipment } from '@/types'

export const KINDS: ApplianceKind[] = ['washer', 'dryer', 'dishwasher', 'vacuum', 'other']

export const kindIcon: Record<string, string> = {
  washer: 'mdi-washing-machine',
  dryer: 'mdi-tumble-dryer',
  dishwasher: 'mdi-dishwasher',
  vacuum: 'mdi-robot-vacuum',
  other: 'mdi-devices',
}

export const commandIcon: Record<string, string> = {
  start: 'mdi-play',
  pause: 'mdi-pause',
  stop: 'mdi-stop',
  return_to_base: 'mdi-home-import-outline',
  locate: 'mdi-map-marker-radius-outline',
  clean_spot: 'mdi-target',
}

/** The defaults the server applies per kind (shown as "Default: …"). Mirrors the server's AUTOMATION_DEFAULTS. */
export const AUTOMATION_DEFAULTS: Record<string, { chores: string; laundry: string }> = {
  washer: { chores: 'make_due', laundry: 'auto' },
  dryer: { chores: 'make_due', laundry: 'auto' },
  dishwasher: { chores: 'make_due', laundry: 'off' },
  vacuum: { chores: 'complete', laundry: 'off' },
  other: { chores: 'off', laundry: 'off' },
}

export function stateLabel(state: string | null | undefined): string {
  if (!state) return t.appliances.states.unknown
  const key = state.toLowerCase()
  if (t.appliances.states[key]) return t.appliances.states[key]
  const words = state.replace(/[_-]+/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

export const commandLabel = (c: string) => t.appliances.commands[c] ?? stateLabel(c)

export function batteryIcon(level: number | null | undefined): string {
  if (level == null) return 'mdi-battery-unknown'
  const step = Math.max(10, Math.min(100, Math.round(level / 10) * 10))
  return step === 100 ? 'mdi-battery' : `mdi-battery-${step}`
}

type LiveLike = { state: string | null; running: boolean; remaining_minutes: number | null; battery: number | null }

/** Compact status for cards and lists: "Running · 42 min left", "Cleaning · 78 %", "Docked". */
export function liveSummary(kind: string, live: LiveLike) {
  const parts = [stateLabel(live.state)]
  if (live.running && live.remaining_minutes != null) parts.push(t.appliances.minutesLeft(live.remaining_minutes))
  if (live.battery != null && (kind === 'vacuum' || live.remaining_minutes == null)) parts.push(t.appliances.battery(live.battery))
  const state = (live.state ?? '').toLowerCase()
  const color = state === 'error' ? 'error' : live.running ? 'primary' : undefined
  return { text: parts.join(' · '), color, running: live.running, off: ['power_off', 'off', 'unavailable'].includes(state) }
}

export const isLinked = (e: Pick<Equipment, 'ha_device_id' | 'ha_entities'>) => !!e.ha_device_id || e.ha_entities.length > 0
