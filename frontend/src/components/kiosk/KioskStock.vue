<script setup lang="ts">
import { computed, ref } from 'vue'
import { LOCALE, t } from '@/i18n'
import { useCatalog } from '@/composables/catalog'
import { formatAmount, formatDate, relativeExpiry } from '@/composables/format'
import { sortBatches } from '@/composables/batches'
import { useKiosk } from '@/composables/kiosk'
import KioskInput from './KioskInput.vue'
import type { StockItem } from '@/types'

// Kiosk "Stock" tab, left side: what is in stock, by location. A product opens its batches, each with
// its own Use 1 / Opened / Throw away, so you take exactly the pack you have in your hand.
const props = defineProps<{ stock: StockItem[] }>()
const kiosk = useKiosk()
const { locationsById } = useCatalog()

const filter = ref('')
const open = ref<number | null>(null)
const fold = (s: string) => s.toLocaleLowerCase(LOCALE).normalize('NFD').replace(/[̀-ͯ]/g, '')

const groups = computed(() => {
  const q = fold(filter.value.trim())
  const items = props.stock.filter((i) => (q ? fold(`${i.product.name} ${i.product.brand ?? ''}`).includes(q) : i.amount > 0))
  const byPlace = new Map<string, StockItem[]>()
  for (const i of items) {
    const place = i.product.location_id != null ? locationsById.value.get(i.product.location_id)?.name ?? t.common.noLocation : t.common.noLocation
    byPlace.set(place, [...(byPlace.get(place) ?? []), i])
  }
  return [...byPlace.entries()]
    .sort(([a], [b]) => (a === t.common.noLocation ? 1 : b === t.common.noLocation ? -1 : a.localeCompare(b, LOCALE)))
    .map(([place, list]) => ({ place, items: list.sort((a, b) => a.product.name.localeCompare(b.product.name, LOCALE)) }))
})

function submit() {
  const all = groups.value.flatMap((g) => g.items)
  if (all.length === 1) open.value = all[0].product.id
}

const statusColor: Record<string, string | undefined> = { expired: 'error', due_soon: 'warning', out: 'grey' }
const place = (id: number | null) => (id != null ? locationsById.value.get(id)?.name ?? null : null)
</script>

<template>
  <div>
    <KioskInput v-model="filter" :placeholder="t.kiosk.filterStock" class="mb-3" @submit="submit" />
    <div v-if="!groups.length" class="text-h6 text-medium-emphasis py-6 text-center">{{ t.kiosk.noMatch }}</div>
    <template v-for="g in groups" :key="g.place">
      <div class="text-overline text-medium-emphasis mt-2">{{ g.place }}</div>
      <v-card variant="flat" border class="mb-2">
        <template v-for="(i, n) in g.items" :key="i.product.id">
          <v-divider v-if="n > 0" />
          <v-list-item class="kiosk-stock__row" @click="open = open === i.product.id ? null : i.product.id">
            <v-list-item-title class="text-h6">{{ i.product.name }}</v-list-item-title>
            <v-list-item-subtitle class="text-body-1">
              {{ formatAmount(i.amount, i.product.unit) }}
              <span v-if="i.amount > 0 && i.next_due" :class="statusColor[i.status] ? `text-${statusColor[i.status]}` : ''"> · {{ relativeExpiry(i.next_due) }}</span>
            </v-list-item-subtitle>
            <template #append>
              <v-icon :icon="open === i.product.id ? 'mdi-chevron-up' : 'mdi-chevron-down'" />
            </template>
          </v-list-item>
          <div v-if="open === i.product.id" class="px-4 pb-4">
            <div v-if="!i.entries.length" class="text-body-1 text-medium-emphasis">{{ t.stock.noEntries }}</div>
            <div v-for="e in sortBatches(i.entries)" :key="e.id" class="kiosk-stock__batch d-flex flex-wrap align-center ga-2 py-2">
              <div class="flex-grow-1" style="min-width: 180px">
                <div class="text-h6">{{ formatAmount(e.amount, i.product.unit) }}</div>
                <div class="text-body-2 text-medium-emphasis">
                  {{ e.due_date ? formatDate(e.due_date) : t.rel.noDue }}<template v-if="e.opened_at"> · {{ t.status.opened }}</template><template v-if="place(e.location_id)"> · {{ place(e.location_id) }}</template>
                </div>
              </div>
              <v-btn size="large" variant="flat" color="primary" prepend-icon="mdi-silverware-fork-knife" @click="kiosk.book(i.product, Math.min(1, e.amount), { mode: 'consume', entryId: e.id })">
                {{ t.stock.useOne }}
              </v-btn>
              <v-btn v-if="!e.opened_at" size="large" variant="tonal" color="info" prepend-icon="mdi-package-variant" @click="kiosk.book(i.product, Math.min(1, e.amount), { mode: 'open', entryId: e.id })">
                {{ t.kiosk.modes.open }}
              </v-btn>
              <v-btn size="large" variant="tonal" color="deep-orange" prepend-icon="mdi-delete-variant" @click="kiosk.book(i.product, e.amount, { mode: 'spoil', entryId: e.id })">
                {{ t.kiosk.modes.spoil }}
              </v-btn>
            </div>
          </div>
        </template>
      </v-card>
    </template>
  </div>
</template>

<style scoped>
.kiosk-stock__row {
  min-height: 64px;
}
.kiosk-stock__batch + .kiosk-stock__batch {
  border-top: 1px dashed rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>
