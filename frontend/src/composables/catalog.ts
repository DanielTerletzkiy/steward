// Shared reference data: products, locations, people. Loaded once, refreshed on live events.
import { computed, reactive } from 'vue'
import { LOCALE } from '@/i18n'
import { api } from '@/api'
import { subscribe } from './live'
import type { Location, Person, Product } from '@/types'

const state = reactive({
  products: [] as Product[],
  locations: [] as Location[],
  people: [] as Person[],
  loaded: false,
})

let started = false

async function loadCatalog() {
  const [products, locations] = await Promise.all([api.products(), api.locations()])
  state.products = products.sort((a, b) => a.name.localeCompare(b.name, LOCALE))
  state.locations = locations.sort((a, b) => a.name.localeCompare(b.name, LOCALE))
}

async function loadPeople() {
  state.people = (await api.people()).sort((a, b) => a.name.localeCompare(b.name, LOCALE))
}

export async function refreshCatalog() {
  await Promise.all([loadCatalog(), loadPeople()])
  state.loaded = true
}

export function useCatalog() {
  if (!started) {
    started = true
    refreshCatalog().catch(() => undefined)
    subscribe(['catalog', 'receipts'], () => loadCatalog().catch(() => undefined))
    subscribe(['people'], () => loadPeople().catch(() => undefined))
  }
  const productsById = computed(() => new Map(state.products.map((p) => [p.id, p])))
  const locationsById = computed(() => new Map(state.locations.map((l) => [l.id, l])))
  const peopleById = computed(() => new Map(state.people.map((p) => [p.id, p])))
  const categories = computed(() =>
    [...new Set(state.products.map((p) => p.category).filter((c): c is string => !!c))].sort((a, b) => a.localeCompare(b, LOCALE)),
  )
  const units = computed(() => [...new Set(['Stk', 'Pck', 'g', 'kg', 'ml', 'l', 'Becher', 'Dose', 'Flasche', ...state.products.map((p) => p.unit)])])
  const personName = (id: string | null | undefined) => (id ? peopleById.value.get(id)?.name ?? id : null)
  return { state, productsById, locationsById, peopleById, categories, units, personName, refresh: refreshCatalog }
}
