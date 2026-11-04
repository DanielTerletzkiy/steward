<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '@/api'
import { LOCALE, t } from '@/i18n'
import { useResource } from '@/composables/resource'
import { useCatalog } from '@/composables/catalog'
import { formatAmount, formatDate } from '@/composables/format'
import { MODE_STYLE, useKiosk, type Card } from '@/composables/kiosk'
import KioskInput from './KioskInput.vue'
import type { Product, StockItem } from '@/types'

// The kiosk's main tab: the last scan large (with +/−, Use all, Undo and the batch it came from),
// earlier scans, and on the right the type-anywhere field, its matches, and tiles for items without a barcode.
const props = defineProps<{ stockById: Map<number, StockItem> }>()
const kiosk = useKiosk()
const { state, productsById, locationsById } = useCatalog()
const { data: frequent } = useResource<Product[]>(() => api.frequentProducts(12), ['stock', 'catalog'], [])
const timeFmt = new Intl.DateTimeFormat(LOCALE, { hour: '2-digit', minute: '2-digit' })

// --- typing ----------------------------------------------------------------

const text = ref('')
const highlight = ref(0)
const fold = (s: string) => s.toLocaleLowerCase(LOCALE).normalize('NFD').replace(/[̀-ͯ]/g, '')
const matches = computed(() => {
  const q = fold(text.value.trim())
  if (!q || /^\d+$/.test(q)) return []
  return state.products
    .map((p) => {
      const name = fold(`${p.name} ${p.brand ?? ''}`)
      const at = name.indexOf(q)
      return { p, rank: at < 0 ? -1 : at === 0 ? 0 : name.includes(` ${q}`) ? 1 : 2 }
    })
    .filter((m) => m.rank >= 0)
    .sort((a, b) => a.rank - b.rank || a.p.name.localeCompare(b.p.name, LOCALE))
    .slice(0, 6)
    .map((m) => m.p)
})
watch(matches, () => (highlight.value = 0))

// A typed code: digits, a known barcode, or a mode card. Anything else is a product search.
const looksLikeCode = (s: string) =>
  /^\d{6,}$/.test(s) || /^STEWARD-MODE-/i.test(s) || state.products.some((p) => p.barcodes?.some((b) => b.code === s))

function submit(value: string) {
  if (!value) return
  if (looksLikeCode(value)) {
    kiosk.onScan(value)
  } else if (matches.value.length) {
    pick(matches.value[Math.min(highlight.value, matches.value.length - 1)])
  } else if (!/\s/.test(value) && value.length >= 6 && /\d/.test(value)) {
    kiosk.onScan(value) // some other code (e.g. a shop's own label)
  }
}
function move(dir: 1 | -1) {
  const n = matches.value.length
  if (n) highlight.value = (highlight.value + dir + n) % n
}
function pick(p: Product) {
  text.value = ''
  ;(document.activeElement as HTMLElement | null)?.blur()
  kiosk.book(p)
}

// --- the card ----------------------------------------------------------------

const card = computed(() => kiosk.current.value)
const productImage = (id: number) => productsById.value.get(id)?.image_url ?? null
const amountText = (c: Card) => formatAmount(kiosk.total(c), c.unit)
const leftText = (c: Card) => {
  const left = kiosk.inStock(c.productId)
  return left > 0 ? t.kiosk.left(formatAmount(left, c.unit)) : t.kiosk.noneLeft
}
const batchText = (c: Card, id: number) => {
  const e = c.batches.find((b) => b.id === id)
  if (!e) return ''
  const place = e.location_id != null ? locationsById.value.get(e.location_id)?.name : null
  return [e.due_date ? formatDate(e.due_date) : t.rel.noDue, e.opened_at ? t.status.opened : null, place].filter(Boolean).join(' · ')
}

const correcting = ref(false)
const correctAmount = ref<number | string>(1)
async function saveCorrection() {
  if (await kiosk.correctStock(Number(String(correctAmount.value).replace(',', '.')))) correcting.value = false
}
</script>

<template>
  <div class="kiosk-scan">
    <section class="kiosk-scan__main">
      <!-- Nothing in stock -->
      <v-card v-if="kiosk.problem.value" variant="flat" border class="pa-6 mb-4 kiosk-scan__problem">
        <div class="d-flex align-center ga-4">
          <v-icon icon="mdi-alert-circle-outline" size="56" color="error" />
          <div class="text-h5">{{ t.kiosk.notInStock(kiosk.problem.value.name) }}</div>
        </div>
        <div class="d-flex flex-wrap ga-3 mt-5">
          <v-btn color="primary" variant="flat" size="x-large" prepend-icon="mdi-pencil" @click="correctAmount = 1; correcting = true">{{ t.kiosk.correct }}</v-btn>
          <v-btn variant="tonal" size="x-large" @click="kiosk.problem.value = null">{{ t.kiosk.ignore }}</v-btn>
        </div>
      </v-card>

      <!-- The last scan -->
      <v-card v-else-if="card" :key="card.key" variant="flat" border class="pa-6 mb-4" :class="{ 'kiosk-scan--undone': card.undone }">
        <div class="d-flex align-center ga-5">
          <v-avatar size="112" rounded="lg" :color="MODE_STYLE[card.mode].color" variant="tonal">
            <v-img v-if="productImage(card.productId)" :src="productImage(card.productId)!" cover />
            <span v-else class="text-h3 font-weight-bold">{{ card.name.charAt(0).toUpperCase() }}</span>
          </v-avatar>
          <div class="flex-grow-1" style="min-width: 0">
            <div class="text-h6 text-medium-emphasis d-flex align-center ga-2">
              <v-icon :icon="MODE_STYLE[card.mode].icon" size="22" />
              <template v-if="card.undone">{{ t.kiosk.undone }}</template>
              <template v-else>{{ t.kiosk.did[card.mode] }} · {{ amountText(card) }}</template>
              <v-chip v-if="card.bookings.length > 1" size="small" label :color="MODE_STYLE[card.mode].color">{{ t.kiosk.times(card.bookings.length) }}</v-chip>
            </div>
            <div class="text-h3 font-weight-bold kiosk-scan__name">{{ card.name }}</div>
            <div class="d-flex flex-wrap align-center ga-2 mt-2">
              <span class="text-h5">{{ leftText(card) }}</span>
              <v-chip v-if="card.onList || stockById.get(card.productId)?.below_min" color="secondary" variant="tonal" prepend-icon="mdi-cart-outline" label>
                {{ t.kiosk.onList }}
              </v-chip>
            </div>
          </div>
        </div>
        <!-- Which batch it came from; tap another to take it from there instead -->
        <div v-if="!card.undone && card.batches.length" class="mt-5">
          <div class="text-body-1 text-medium-emphasis mb-2">{{ t.kiosk.fromBatch }}</div>
          <div class="d-flex flex-wrap ga-2">
            <v-chip
              v-for="b in card.batches"
              :key="b.id"
              size="x-large"
              label
              :variant="kiosk.usedEntryIds(card).has(b.id) ? 'flat' : 'outlined'"
              :color="kiosk.usedEntryIds(card).has(b.id) ? MODE_STYLE[card.mode].color : undefined"
              :prepend-icon="kiosk.usedEntryIds(card).has(b.id) ? 'mdi-check' : 'mdi-calendar-outline'"
              @click="!kiosk.usedEntryIds(card).has(b.id) && kiosk.moveToBatch(card, b.id)"
            >
              {{ batchText(card, b.id) }}
            </v-chip>
          </div>
        </div>
        <div v-if="!card.undone" class="d-flex flex-wrap align-center ga-3 mt-6">
          <v-btn icon="mdi-minus" size="x-large" variant="tonal" :aria-label="t.kiosk.less" :title="t.kiosk.less" @click="kiosk.minus(card)" />
          <v-btn icon="mdi-plus" size="x-large" variant="tonal" :aria-label="t.kiosk.more" :title="t.kiosk.more" @click="kiosk.plus(card)" />
          <v-btn v-if="card.mode === 'consume' && kiosk.inStock(card.productId) > 0" size="x-large" variant="tonal" prepend-icon="mdi-check-all" @click="kiosk.useAll(card)">
            {{ t.kiosk.useAll }}
          </v-btn>
          <v-spacer />
          <v-btn size="x-large" variant="text" prepend-icon="mdi-undo" @click="kiosk.undoCard(card)">{{ t.kiosk.undo }}</v-btn>
        </div>
      </v-card>

      <!-- Waiting for a scan -->
      <div v-else class="text-center py-10">
        <v-progress-circular v-if="kiosk.busy.value" indeterminate size="72" :color="kiosk.style.value.color" />
        <v-icon v-else icon="mdi-barcode-scan" size="96" :color="kiosk.style.value.color" />
        <div class="text-h4 font-weight-bold mt-4">{{ t.kiosk.ready }}</div>
        <div class="text-h6 text-medium-emphasis">{{ t.kiosk.readyHint }}</div>
      </div>
      <div v-if="kiosk.mode.value !== 'consume'" class="text-body-1 text-medium-emphasis mb-4">
        <v-icon icon="mdi-timer-sand" size="18" /> {{ t.kiosk.backSoon }}
      </div>

      <template v-if="kiosk.earlier.value.length">
        <div class="text-overline text-medium-emphasis">{{ t.kiosk.earlier }}</div>
        <v-list class="bg-transparent py-0">
          <v-list-item v-for="c in kiosk.earlier.value" :key="c.key" class="px-0" :class="{ 'kiosk-scan--undone': c.undone }">
            <template #prepend>
              <v-avatar :color="MODE_STYLE[c.mode].color" variant="tonal" size="40"><v-icon :icon="MODE_STYLE[c.mode].icon" size="20" /></v-avatar>
            </template>
            <v-list-item-title class="text-h6">{{ c.name }}</v-list-item-title>
            <v-list-item-subtitle>
              {{ c.undone ? t.kiosk.undone : `${t.kiosk.did[c.mode]} · ${amountText(c)}` }} · {{ timeFmt.format(c.at) }}
            </v-list-item-subtitle>
            <template v-if="!c.undone" #append>
              <v-btn variant="text" size="large" prepend-icon="mdi-undo" @click="kiosk.undoCard(c)">{{ t.kiosk.undo }}</v-btn>
            </template>
          </v-list-item>
        </v-list>
      </template>
    </section>

    <aside class="kiosk-scan__side">
      <KioskInput v-model="text" :placeholder="t.kiosk.typeHere" icon="mdi-keyboard-outline" class="mb-3" @submit="submit" @move="move" />
      <v-list v-if="matches.length" class="kiosk-scan__matches mb-4" rounded="lg">
        <v-list-item
          v-for="(p, i) in matches"
          :key="p.id"
          :active="i === highlight"
          :color="kiosk.style.value.color"
          :title="p.name"
          :subtitle="formatAmount(kiosk.inStock(p.id), p.unit)"
          @click="pick(p)"
        >
          <template #append><v-icon :icon="kiosk.style.value.icon" /></template>
        </v-list-item>
      </v-list>
      <div v-else-if="text.trim()" class="text-body-1 text-medium-emphasis mb-4">{{ /^\d+$/.test(text.trim()) ? t.kiosk.enterForCode : t.kiosk.noMatch }}</div>
      <template v-if="frequent.length">
        <div class="text-overline text-medium-emphasis">{{ t.kiosk.frequent }}</div>
        <div class="kiosk-scan__tiles">
          <v-btn
            v-for="p in frequent"
            :key="p.id"
            variant="tonal"
            :color="kiosk.style.value.color"
            rounded="lg"
            height="96"
            stacked
            class="kiosk-scan__tile"
            @click="kiosk.book(p)"
          >
            <v-avatar v-if="p.image_url" size="40" rounded="lg" class="mb-1"><v-img :src="p.image_url" cover /></v-avatar>
            <span class="kiosk-scan__tile-name">{{ p.name }}</span>
            <span class="text-caption text-medium-emphasis">{{ formatAmount(kiosk.inStock(p.id), p.unit) }}</span>
          </v-btn>
        </div>
      </template>
    </aside>

    <v-dialog v-model="correcting" max-width="420">
      <v-card v-if="kiosk.problem.value" :title="t.kiosk.correctTitle(kiosk.problem.value.name)">
        <v-card-text>
          <v-text-field v-model="correctAmount" type="number" min="0" step="any" :suffix="kiosk.problem.value.unit" autofocus hide-details @keydown.enter="saveCorrection" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="correcting = false">{{ t.common.cancel }}</v-btn>
          <v-btn color="primary" variant="flat" @click="saveCorrection">{{ t.common.save }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.kiosk-scan {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
  gap: 24px;
}
@media (max-width: 900px) {
  .kiosk-scan {
    grid-template-columns: minmax(0, 1fr);
  }
}
.kiosk-scan__name {
  overflow-wrap: anywhere;
  line-height: 1.15;
}
.kiosk-scan--undone {
  opacity: 0.5;
}
.kiosk-scan__problem {
  border-color: rgb(var(--v-theme-error)) !important;
}
.kiosk-scan__matches :deep(.v-list-item-title) {
  font-size: 1.2rem;
  font-weight: 600;
}
.kiosk-scan__matches :deep(.v-list-item) {
  min-height: 60px;
}
.kiosk-scan__tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 10px;
}
.kiosk-scan__tile {
  min-width: 0 !important;
  letter-spacing: 0;
}
.kiosk-scan__tile-name {
  font-size: 1rem;
  font-weight: 600;
  white-space: normal;
  line-height: 1.2;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
</style>
