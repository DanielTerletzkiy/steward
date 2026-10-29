<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { api } from '@/api'
import { LOCALE, t } from '@/i18n'
import { useResource } from '@/composables/resource'
import { useCatalog } from '@/composables/catalog'
import { consume, openProduct } from '@/composables/stockActions'
import { formatAmount, formatDate, formatEuro, relativeExpiry } from '@/composables/format'
import { attempt, notify } from '@/composables/notify'
import EmptyState from '@/components/EmptyState.vue'
import StatusChip from '@/components/StatusChip.vue'
import PurchaseDialog from '@/components/PurchaseDialog.vue'
import ProductDialog from '@/components/ProductDialog.vue'
import type { Product, StockItem } from '@/types'

const { data: items, loading, error, reload } = useResource<StockItem[]>(() => api.stock(true), ['stock', 'catalog'], [])
const { state, locationsById } = useCatalog()
const { smAndUp } = useDisplay()

type Filter = 'all' | 'in_stock' | 'expiring' | 'below_min' | 'out'
function load<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(`steward.stock.${key}`)
    return v ? (JSON.parse(v) as T) : fallback
  } catch {
    return fallback
  }
}
const search = ref('')
const filter = ref<Filter>(load('filter', 'all'))
const location = ref<number | null>(load('location', null))
const grouped = ref<boolean>(load('grouped', true))
watch([filter, location, grouped], () => {
  try {
    localStorage.setItem('steward.stock.filter', JSON.stringify(filter.value))
    localStorage.setItem('steward.stock.location', JSON.stringify(location.value))
    localStorage.setItem('steward.stock.grouped', JSON.stringify(grouped.value))
  } catch {
    /* storage unavailable */
  }
})

const filters: { value: Filter; label: string; icon: string }[] = [
  { value: 'all', label: t.stock.allStatus, icon: 'mdi-view-list' },
  { value: 'in_stock', label: t.stock.filterInStock, icon: 'mdi-package-variant-closed' },
  { value: 'expiring', label: t.stock.filterExpiring, icon: 'mdi-clock-alert-outline' },
  { value: 'below_min', label: t.stock.filterBelowMin, icon: 'mdi-arrow-down-bold-circle-outline' },
  { value: 'out', label: t.stock.filterOut, icon: 'mdi-package-variant' },
]

const counts = computed(() => ({
  all: items.value.length,
  in_stock: items.value.filter((i) => i.amount > 0).length,
  expiring: items.value.filter((i) => i.status === 'expired' || i.status === 'due_soon').length,
  below_min: items.value.filter((i) => i.below_min).length,
  out: items.value.filter((i) => i.status === 'out').length,
}))

const visible = computed(() => {
  const q = search.value.trim().toLowerCase()
  return items.value
    .filter((i) => {
      if (location.value != null && i.product.location_id !== location.value && !i.entries.some((e) => e.location_id === location.value)) return false
      if (q && !`${i.product.name} ${i.product.brand ?? ''} ${i.product.category ?? ''}`.toLowerCase().includes(q)) return false
      switch (filter.value) {
        case 'in_stock': return i.amount > 0
        case 'expiring': return i.status === 'expired' || i.status === 'due_soon'
        case 'below_min': return i.below_min
        case 'out': return i.status === 'out'
        default: return true
      }
    })
    .sort((a, b) => Number(a.amount <= 0) - Number(b.amount <= 0) || a.product.name.localeCompare(b.product.name, LOCALE))
})

const groups = computed(() => {
  if (!grouped.value) return [{ key: 'all', name: '', icon: '', items: visible.value }]
  const map = new Map<number | null, StockItem[]>()
  for (const i of visible.value) {
    const k = i.product.location_id
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(i)
  }
  return [...map.entries()]
    .map(([id, list]) => {
      const loc = id != null ? locationsById.value.get(id) : undefined
      return {
        key: String(id),
        name: loc?.name ?? t.common.noLocation,
        icon: loc?.is_freezer ? 'mdi-snowflake' : locationIcon(loc?.name),
        items: list,
      }
    })
    .sort((a, b) => a.name.localeCompare(b.name, LOCALE))
})

function locationIcon(name?: string) {
  // Location names are user data, so match English and German words.
  const n = (name ?? '').toLowerCase()
  const has = (...words: string[]) => words.some((w) => n.includes(w))
  if (has('freez', 'gefrier', 'tiefkühl')) return 'mdi-snowflake'
  if (has('fridge', 'kühl')) return 'mdi-fridge-outline'
  if (has('bath', 'bad')) return 'mdi-shower'
  if (has('drink', 'beverage', 'getränk')) return 'mdi-bottle-wine-outline'
  if (has('household', 'cleaning', 'haushalt')) return 'mdi-spray-bottle'
  if (has('pantry', 'cupboard', 'vorrat', 'schrank')) return 'mdi-cupboard-outline'
  return 'mdi-map-marker-outline'
}

const purchaseFor = ref<Product | null>(null)
const purchaseOpen = ref(false)
async function moveEntry(entryId: number, locationId: number | null) {
  if (!(await attempt(() => api.moveEntry(entryId, locationId)))) return
  notify(locationId != null ? t.stock.moved(locationsById.value.get(locationId)?.name ?? '') : t.stock.movedNowhere)
  reload()
}

function openPurchase(p: Product) {
  purchaseFor.value = p
  purchaseOpen.value = true
}
const editFor = ref<Product | null>(null)
const editOpen = ref(false)
function openEdit(p: Product | null) {
  editFor.value = p
  editOpen.value = true
}
const expanded = ref<number | null>(null)
</script>

<template>
  <div class="page has-fab">
    <div class="d-flex align-center mb-4">
      <div>
        <div class="page-title">{{ t.stock.title }}</div>
        <div class="text-body-2 text-medium-emphasis">{{ t.stock.count(visible.length) }}</div>
      </div>
      <v-spacer />
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openEdit(null)">
        {{ smAndUp ? t.stock.newProduct : t.common.create }}
      </v-btn>
    </div>

    <v-row dense class="mb-1">
      <v-col cols="12" md="6">
        <v-text-field v-model="search" :placeholder="t.stock.searchPlaceholder" prepend-inner-icon="mdi-magnify" clearable hide-details density="compact" variant="solo-filled" flat rounded="pill" />
      </v-col>
      <v-col cols="8" md="4">
        <v-select v-model="location" :items="state.locations" item-title="name" item-value="id" :placeholder="t.stock.allLocations" prepend-inner-icon="mdi-map-marker-outline" clearable hide-details density="compact" variant="solo-filled" flat rounded="pill" />
      </v-col>
      <v-col cols="4" md="2" class="d-flex align-center justify-end">
        <v-btn-toggle v-model="grouped" mandatory density="compact" rounded="pill" variant="outlined" divided color="primary">
          <v-btn :value="true" icon="mdi-format-list-group" :title="t.stock.group" />
          <v-btn :value="false" icon="mdi-format-list-bulleted" />
        </v-btn-toggle>
      </v-col>
    </v-row>

    <v-chip-group v-model="filter" mandatory selected-class="text-primary" class="mb-2">
      <v-chip v-for="f in filters" :key="f.value" :value="f.value" :prepend-icon="f.icon" variant="outlined" size="default" filter>
        {{ f.label }}<span class="ml-1 text-medium-emphasis">{{ counts[f.value] }}</span>
      </v-chip>
    </v-chip-group>

    <v-alert v-if="error" type="error" variant="tonal" :text="error" class="mb-4">
      <template #append><v-btn variant="text" @click="reload">{{ t.app.retry }}</v-btn></template>
    </v-alert>

    <v-skeleton-loader v-if="loading && !items.length" type="list-item-two-line@6" class="rounded-xl" />

    <EmptyState v-else-if="!visible.length" icon="mdi-fridge-off-outline" :title="t.stock.empty" :text="t.stock.emptyHint">
      <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="openEdit(null)">{{ t.stock.newProduct }}</v-btn>
    </EmptyState>

    <template v-else>
      <v-card v-for="g in groups" :key="g.key" variant="flat" border class="mb-4">
        <v-card-item v-if="grouped" :prepend-icon="g.icon" class="pb-0">
          <v-card-title class="text-subtitle-1 font-weight-medium">{{ g.name }}</v-card-title>
          <template #append><span class="text-caption text-medium-emphasis">{{ g.items.length }}</span></template>
        </v-card-item>
        <v-list lines="two" bg-color="transparent" class="py-1">
          <template v-for="(i, idx) in g.items" :key="i.product.id">
            <v-divider v-if="idx > 0" inset />
            <v-list-item class="py-2" :class="i.amount <= 0 ? 'opacity-70' : ''" @click="expanded = expanded === i.product.id ? null : i.product.id">
              <template #prepend>
                <v-avatar :color="i.status === 'expired' ? 'error' : i.status === 'due_soon' ? 'warning' : i.amount > 0 ? 'primary' : 'grey'" variant="tonal" class="font-weight-bold">
                  {{ i.product.name.charAt(0).toUpperCase() }}
                </v-avatar>
              </template>
              <v-list-item-title class="font-weight-medium wrap">
                {{ i.product.name }}
                <span v-if="i.product.brand" class="text-medium-emphasis font-weight-regular text-body-2">· {{ i.product.brand }}</span>
              </v-list-item-title>
              <v-list-item-subtitle class="d-flex flex-wrap align-center ga-1 mt-1">
                <span class="text-tabular font-weight-medium text-high-emphasis">{{ formatAmount(i.amount, i.product.unit) }}</span>
                <span v-if="i.opened > 0">({{ formatAmount(i.opened, '') }} {{ t.status.opened }})</span>
                <span v-if="i.amount > 0 && i.next_due" :class="i.status === 'expired' ? 'text-error' : i.status === 'due_soon' ? 'text-warning' : ''">· {{ relativeExpiry(i.next_due) }}</span>
                <v-chip v-if="i.below_min && i.amount > 0" color="warning" variant="tonal" size="x-small" label class="ml-1">{{ t.status.below_min }}</v-chip>
              </v-list-item-subtitle>
              <template #append>
                <div class="d-flex align-center ga-1" @click.stop>
                  <StatusChip v-if="smAndUp" :status="i.below_min && i.status === 'out' ? 'below_min' : i.status" class="mr-2" />
                  <v-btn icon="mdi-minus" variant="tonal" :size="smAndUp ? 'small' : 'x-small'" :disabled="i.amount <= 0" :title="t.stock.consume" @click="consume(i.product, 1)" />
                  <v-btn icon="mdi-plus" variant="tonal" color="primary" :size="smAndUp ? 'small' : 'x-small'" :title="t.stock.purchase" @click="openPurchase(i.product)" />
                  <v-menu location="bottom end">
                    <template #activator="{ props }"><v-btn v-bind="props" icon="mdi-dots-vertical" variant="text" size="small" /></template>
                    <v-list density="compact">
                      <v-list-item prepend-icon="mdi-delete-variant" :title="t.stock.spoil" :disabled="i.amount <= 0" @click="consume(i.product, 1, true)" />
                      <v-list-item prepend-icon="mdi-package-variant-closed-remove" :title="t.stock.open" :disabled="i.amount - i.opened <= 0" @click="openProduct(i.product, 1)" />
                      <v-divider />
                      <v-list-item prepend-icon="mdi-pencil" :title="t.common.edit" @click="openEdit(i.product)" />
                    </v-list>
                  </v-menu>
                </div>
              </template>
            </v-list-item>
            <v-expand-transition>
              <div v-if="expanded === i.product.id" class="px-4 pb-3">
                <v-sheet rounded="lg" color="surface-container" class="pa-3">
                  <div class="d-flex flex-wrap ga-2 mb-2">
                    <StatusChip v-if="!smAndUp" :status="i.status" />
                    <v-chip v-if="i.product.category" variant="outlined" prepend-icon="mdi-tag-outline">{{ i.product.category }}</v-chip>
                    <v-chip v-if="i.value" variant="outlined" prepend-icon="mdi-currency-eur">{{ t.stock.value }} {{ formatEuro(i.value) }}</v-chip>
                    <v-chip v-if="i.product.min_stock" variant="outlined" prepend-icon="mdi-arrow-collapse-down">{{ t.stock.minStock }} {{ formatAmount(i.product.min_stock, i.product.unit) }}</v-chip>
                  </div>
                  <div class="text-caption text-medium-emphasis mb-1">{{ t.stock.entries }}</div>
                  <div v-if="!i.entries.length" class="text-body-2">{{ t.stock.noEntries }}</div>
                  <v-table v-else density="compact" class="bg-transparent">
                    <tbody>
                      <tr v-for="e in i.entries" :key="e.id">
                        <td class="text-tabular">{{ formatAmount(e.amount, i.product.unit) }}</td>
                        <td>{{ e.due_date ? formatDate(e.due_date) : '–' }}</td>
                        <td>
                          <v-menu location="bottom">
                            <template #activator="{ props }">
                              <v-btn v-bind="props" variant="text" size="small" class="px-1 text-none" :prepend-icon="e.location_id != null && locationsById.get(e.location_id)?.is_freezer ? 'mdi-snowflake' : 'mdi-map-marker-outline'" :title="t.stock.moveTo">
                                {{ e.location_id != null ? locationsById.get(e.location_id)?.name : t.common.noLocation }}
                              </v-btn>
                            </template>
                            <v-list density="compact">
                              <v-list-subheader>{{ t.stock.moveTo }}</v-list-subheader>
                              <v-list-item v-for="l in state.locations" :key="l.id" :title="l.name" :active="l.id === e.location_id" :prepend-icon="l.is_freezer ? 'mdi-snowflake' : 'mdi-map-marker-outline'" @click="moveEntry(e.id, l.id)" />
                              <v-list-item :title="t.common.noLocation" :active="e.location_id == null" prepend-icon="mdi-map-marker-off-outline" @click="moveEntry(e.id, null)" />
                            </v-list>
                          </v-menu>
                        </td>
                        <td>{{ e.unit_price != null ? formatEuro(e.unit_price) : '' }}</td>
                        <td><v-icon v-if="e.opened_at" icon="mdi-package-variant-closed-remove" size="16" :title="t.status.opened" /></td>
                      </tr>
                    </tbody>
                  </v-table>
                </v-sheet>
              </div>
            </v-expand-transition>
          </template>
        </v-list>
      </v-card>
    </template>

    <PurchaseDialog v-model="purchaseOpen" :product="purchaseFor" />
    <ProductDialog v-model="editOpen" :product="editFor" />
    <v-btn class="scan-fab" color="primary" size="large" rounded="lg" elevation="4" prepend-icon="mdi-barcode-scan" to="/scan" height="56">{{ t.nav.scan }}</v-btn>
  </div>
</template>
