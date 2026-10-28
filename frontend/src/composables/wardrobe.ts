// Wardrobe helpers: the shared vocabulary, translated labels and actions with undo snackbars.
import { shallowRef } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { attempt, notify, notifyError } from './notify'
import type { Garment, GarmentState, WardrobeVocabulary } from '@/types'

const vocabulary = shallowRef<WardrobeVocabulary | null>(null)
let loading: Promise<void> | null = null

/** The fixed value lists (categories, states, colors, …), loaded once per session. */
export function useVocabulary() {
  if (!vocabulary.value && !loading) {
    loading = api
      .wardrobeVocabulary()
      .then((v) => void (vocabulary.value = v))
      .catch(() => void (loading = null))
  }
  return vocabulary
}

const lookup = (map: Record<string, string>, key: string | null | undefined) => (key ? map[key] ?? key : '')

export const label = {
  category: (v: string | null | undefined) => lookup(t.wardrobe.categories, v),
  layer: (v: string | null | undefined) => lookup(t.wardrobe.layers, v),
  state: (v: string | null | undefined) => lookup(t.wardrobe.states, v),
  rain: (v: string | null | undefined) => lookup(t.wardrobe.rainLevels, v),
  use: (v: string | null | undefined) => lookup(t.wardrobe.useNames, v),
  season: (v: string | null | undefined) => lookup(t.wardrobe.seasonNames, v),
  pattern: (v: string | null | undefined) => lookup(t.wardrobe.patterns, v),
  color: (v: string | null | undefined) => lookup(t.wardrobe.colorNames, v),
  source: (v: string | null | undefined) => lookup(t.wardrobe.sources, v),
}

/** Swatch colors for the vocabulary's color names. */
const SWATCH: Record<string, string> = {
  black: '#1b1b1b', white: '#f7f7f5', grey: '#9e9e9e', navy: '#1f2a4d', blue: '#2f6fd1', 'light blue': '#9cc8ef',
  beige: '#d9c6a5', brown: '#7a5233', olive: '#6b6b2e', green: '#3a8a4a', red: '#c8332d', burgundy: '#7b1e33',
  pink: '#f2a7c3', purple: '#7a4fb0', yellow: '#f2cf3b', orange: '#ec8a2f',
}
export const swatch = (color: string) => SWATCH[color] ?? '#9e9e9e'

export const stateColor: Record<string, string> = {
  clean: 'success', worn: 'info', laundry: 'warning', repair: 'error', lent: 'secondary', stored: 'grey',
}
export const stateIcon: Record<string, string> = {
  clean: 'mdi-check-circle-outline', worn: 'mdi-tshirt-crew-outline', laundry: 'mdi-washing-machine', repair: 'mdi-needle',
  lent: 'mdi-account-arrow-right-outline', stored: 'mdi-archive-outline',
}
export const layerIcon: Record<string, string> = {
  base: 'mdi-tshirt-crew-outline', mid: 'mdi-tshirt-v-outline', outer: 'mdi-coat-rack', bottom: 'mdi-human-male',
  full: 'mdi-human-female', shoes: 'mdi-shoe-sneaker', accessory: 'mdi-hat-fedora',
}
export const sourceIcon: Record<string, string> = { manual: 'mdi-hand-back-right-outline', rules: 'mdi-lightbulb-outline', ai: 'mdi-creation' }

/** Log a wear for the pieces; say how many went to the laundry. */
export async function wearToday(ids: number[]) {
  const res = await attempt(() => api.wear(ids))
  if (!res) return false
  const toLaundry = res.filter((g) => g.state === 'laundry').length
  notify(toLaundry ? `${t.wardrobe.wornMsg(ids.length)} · ${t.wardrobe.toLaundryMsg(toLaundry)}` : t.wardrobe.wornMsg(ids.length))
  return true
}

/** Wash the given pieces, with an Undo that puts them back into the laundry exactly as they were. */
export async function laundryDone(pieces: Pick<Garment, 'id' | 'state' | 'wears_since_wash'>[]) {
  const before = pieces.map((g) => ({ id: g.id, state: g.state, wears_since_wash: g.wears_since_wash }))
  const res = await attempt(() => api.laundryDone(before.length ? before.map((g) => g.id) : undefined))
  if (!res) return false
  notify(t.wardrobe.washedMsg(res.washed), {
    action: before.length
      ? {
          label: t.common.undo,
          run: async () => {
            try {
              await Promise.all(before.map((g) => api.updateGarment(g.id, { state: g.state, wears_since_wash: g.wears_since_wash })))
              notify(t.common.undone)
            } catch (e) {
              notifyError(e)
            }
          },
        }
      : undefined,
  })
  return true
}

/** Move a piece to another state, with an Undo back to the previous one. */
export async function setGarmentState(g: Garment, state: GarmentState) {
  if (g.state === state) return
  const previous = { state: g.state, wears_since_wash: g.wears_since_wash }
  const res = await attempt(() => api.updateGarment(g.id, { state }))
  if (!res) return
  notify(t.wardrobe.stateMsg(g.name, label.state(state)), {
    action: { label: t.common.undo, run: async () => void (await attempt(() => api.updateGarment(g.id, previous))) },
  })
}
