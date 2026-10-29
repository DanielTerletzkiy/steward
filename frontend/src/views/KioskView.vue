<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '@/api'
import { LOCALE, t } from '@/i18n'
import { auth } from '@/composables/auth'
import { connected } from '@/composables/live'
import { useResource } from '@/composables/resource'
import { useCatalog } from '@/composables/catalog'
import { useWedgeScanner } from '@/composables/barcode'
import { beepError, beepOk } from '@/composables/sound'
import { formatAmount } from '@/composables/format'
import ScanResultCard from '@/components/ScanResultCard.vue'
import type { Product, ScanLookup, StockItem } from '@/types'

// The kitchen terminal: a full-screen page for a fixed screen with a USB barcode scanner.
// Every scan is booked right away; the last one shows large, with +/−, "Use all" and Undo.
type KioskMode = 'consume' | 'purchase' | 'open' | 'spoil' | 'shopping'
const MODES: KioskMode[] = ['consume', 'purchase', 'open', 'spoil', 'shopping']
const STYLE: Record<KioskMode, { color: string; icon: string }> = {
  consume: { color: 'primary', icon: 'mdi-silverware-fork-knife' },
  purchase: { color: 'success', icon: 'mdi-cart-arrow-down' },
  open: { color: 'info', icon: 'mdi-package-variant' },
  spoil: { color: 'deep-orange', icon: 'mdi-delete-variant' },
  shopping: { color: 'secondary', icon: 'mdi-cart-plus' },
}
const NEEDS_STOCK: KioskMode[] = ['consume', 'open', 'spoil']
const RESET_MS = 60_000 // other modes fall back to Use
const MERGE_MS = 15_000 // the same product again within this adds to the card
const IDLE_MS = 5 * 60_000 // then the page goes dark

const { state, productsById } = useCatalog()
const { data: stock } = useResource<StockItem[]>(() => api.stock(true), ['stock', 'catalog'], [])
const stockById = computed(() => new Map(stock.value.map((s) => [s.product.id, s])))
const { data: frequent } = useResource<Product[]>(() => api.frequentProducts(12), ['stock', 'catalog'], [])

const mode = ref<KioskMode>('consume')
const style = computed(() => STYLE[mode.value])

interface Booking {
  txnIds: number[]
  shoppingItemId?: number
  amount: number
}
interface Card {
  key: number
  productId: number
  name: string
  unit: string
  mode: KioskMode
  bookings: Booking[]
  at: number
  onList: boolean
  undone: boolean
}
let nextKey = 1
const current = ref<Card | null>(null)
const earlier = ref<Card[]>([])
const total = (c: Card) => c.bookings.reduce((sum, b) => sum + b.amount, 0)
const inStock = (productId: number) => stockById.value.get(productId)?.amount ?? 0

// --- feedback, clock, idle -------------------------------------------------

const flash = ref<'ok' | 'error' | null>(null)
const message = ref<string | null>(null)
let flashTimer: number | undefined
function signal(kind: 'ok' | 'error', text: string | null = null) {
  flash.value = kind
  message.value = text
  if (kind === 'ok') beepOk()
  else beepError()
  window.clearTimeout(flashTimer)
  flashTimer = window.setTimeout(() => (flash.value = null), 700)
}
const errorText = (e: unknown) => (!connected.value ? t.kiosk.offline : e instanceof Error ? e.message : t.kiosk.failed)

const now = ref(Date.now())
let lastActive = Date.now()
let lastModeUse = Date.now()
const sleeping = ref(false)
const clock = new Intl.DateTimeFormat(LOCALE, { hour: '2-digit', minute: '2-digit' })
const timeFmt = new Intl.DateTimeFormat(LOCALE, { hour: '2-digit', minute: '2-digit' })

function activity() {
  lastActive = Date.now()
  sleeping.value = false
}
let ticker: number | undefined
onMounted(() => {
  ticker = window.setInterval(() => {
    now.value = Date.now()
    if (mode.value !== 'consume' && now.value - lastModeUse > RESET_MS) mode.value = 'consume'
    if (!sleeping.value && now.value - lastActive > IDLE_MS) sleeping.value = true
  }, 1000)
  window.addEventListener('keydown', activity, true)
  window.addEventListener('pointerdown', activity, true)
})
onBeforeUnmount(() => {
  window.clearInterval(ticker)
  window.clearTimeout(flashTimer)
  window.removeEventListener('keydown', activity, true)
  window.removeEventListener('pointerdown', activity, true)
})

function setMode(m: KioskMode) {
  mode.value = m
  lastModeUse = Date.now()
}

// --- booking ----------------------------------------------------------------

async function bookDirect(productId: number, m: KioskMode, amount: number): Promise<Booking> {
  switch (m) {
    case 'purchase':
      return { txnIds: (await api.purchase({ product_id: productId, amount })).txn_ids, amount }
    case 'consume':
    case 'spoil': {
      const res = await api.consume(productId, amount, m === 'spoil')
      return { txnIds: res.txn_ids, amount: res.consumed }
    }
    case 'open':
      return { txnIds: (await api.open(productId, amount)).txn_ids, amount }
    case 'shopping': {
      const lists = await api.shoppingLists()
      const item = await api.addShoppingItem(lists[0].id, { product_id: productId, amount })
      return { txnIds: [], shoppingItemId: item.id, amount }
    }
  }
}

async function unbook(b: Booking) {
  for (const id of [...b.txnIds].reverse()) await api.undo(id)
  if (b.shoppingItemId) await api.deleteShoppingItem(b.shoppingItemId)
}

function record(product: { id: number; name: string; unit: string }, m: KioskMode, booking: Booking, onList: boolean) {
  const cur = current.value
  if (cur && !cur.undone && cur.productId === product.id && cur.mode === m && Date.now() - cur.at < MERGE_MS) {
    cur.bookings.push(booking)
    cur.at = Date.now()
    cur.onList = onList
  } else {
    if (cur) earlier.value = [cur, ...earlier.value].slice(0, 8)
    current.value = { key: nextKey++, productId: product.id, name: product.name, unit: product.unit, mode: m, bookings: [booking], at: Date.now(), onList, undone: false }
  }
  if (m !== 'consume') lastModeUse = Date.now()
  signal('ok')
}

// Nothing in stock to use: say so, and offer to correct the stock.
const problem = ref<{ id: number; name: string; unit: string } | null>(null)
const correcting = ref(false)
const correctAmount = ref<number | string>(1)

function notInStock(product: { id: number; name: string; unit: string }) {
  problem.value = product
  signal('error')
}

async function saveCorrection() {
  const p = problem.value
  const amount = Number(String(correctAmount.value).replace(',', '.'))
  if (!p || !(amount > 0)) return
  try {
    await api.purchase({ product_id: p.id, amount })
    correcting.value = false
    problem.value = null
    signal('ok', t.kiosk.corrected)
  } catch (e) {
    signal('error', errorText(e))
  }
}

// Scans are handled one at a time, in order, even when they come in fast.
let queue: Promise<void> = Promise.resolve()
const unknown = ref<ScanLookup | null>(null)
const busy = ref(false)

function onScan(raw: string) {
  search.value = ''
  queue = queue.then(() => handleCode(raw.trim()))
}

async function handleCode(code: string) {
  if (!code || unknown.value) return
  busy.value = true
  problem.value = null
  const m = mode.value
  try {
    const res = await api.scan(code, m)
    if (res.mode_switch && MODES.includes(res.mode_switch as KioskMode)) {
      setMode(res.mode_switch as KioskMode)
      signal('ok', t.kiosk.modeSwitched(t.kiosk.modes[res.mode_switch]))
    } else if (res.product_id == null) {
      unknown.value = res
      signal('error', t.kiosk.unknown)
    } else if (res.not_in_stock) {
      const p = productsById.value.get(res.product_id)
      notInStock({ id: res.product_id, name: res.product_name ?? p?.name ?? code, unit: res.unit ?? p?.unit ?? '' })
    } else if (res.done) {
      const booking = { txnIds: res.txn_ids ?? [], shoppingItemId: res.shopping_item_id, amount: res.amount ?? 1 }
      record({ id: res.product_id, name: res.product_name ?? code, unit: res.unit ?? '' }, m, booking, !!res.on_shopping_list)
    } else {
      signal('error', t.kiosk.failed)
    }
  } catch (e) {
    signal('error', errorText(e))
  } finally {
    busy.value = false
  }
}

async function bookProduct(p: Product, amount = 1) {
  const m = mode.value
  problem.value = null
  if (NEEDS_STOCK.includes(m) && inStock(p.id) <= 0) return notInStock(p)
  try {
    const booking = await bookDirect(p.id, m, amount)
    record(p, m, booking, false)
  } catch (e) {
    signal('error', errorText(e))
  }
}

async function plus(card: Card) {
  if (NEEDS_STOCK.includes(card.mode) && inStock(card.productId) <= 0) return signal('error', t.kiosk.noneLeft)
  try {
    card.bookings.push(await bookDirect(card.productId, card.mode, card.bookings.at(-1)?.amount || 1))
    card.at = Date.now()
    signal('ok')
  } catch (e) {
    signal('error', errorText(e))
  }
}

async function minus(card: Card) {
  const last = card.bookings.at(-1)
  if (!last) return
  try {
    await unbook(last)
    card.bookings.pop()
    if (!card.bookings.length) card.undone = true
    signal('ok')
  } catch (e) {
    signal('error', errorText(e))
  }
}

async function useAll(card: Card) {
  const left = inStock(card.productId)
  if (left <= 0) return
  try {
    card.bookings.push(await bookDirect(card.productId, 'consume', left))
    card.at = Date.now()
    signal('ok')
  } catch (e) {
    signal('error', errorText(e))
  }
}

async function undoCard(card: Card) {
  try {
    while (card.bookings.length) {
      await unbook(card.bookings.at(-1)!)
      card.bookings.pop()
    }
    card.undone = true
    signal('ok', t.kiosk.undone)
  } catch (e) {
    signal('error', errorText(e))
  }
}

// Unknown barcode: create or link the product (ScanResultCard in "look up" mode), then book the scan.
function unknownDone() {
  const code = unknown.value?.code
  unknown.value = null
  if (code) queue = queue.then(() => handleCode(code))
}

// --- search with the keyboard ----------------------------------------------

const search = ref('')
const picked = ref<number | null>(null)
function onPick(id: number | null) {
  const p = id != null ? productsById.value.get(id) : undefined
  picked.value = null
  search.value = ''
  ;(document.activeElement as HTMLElement | null)?.blur()
  if (p) bookProduct(p)
}

useWedgeScanner(onScan, { inFields: true })

// --- pairing ---------------------------------------------------------------

const pairCode = ref('')
const wasPaired = (() => {
  try {
    return localStorage.getItem('steward.kiosk.paired') === '1'
  } catch {
    return false
  }
})()
onMounted(() => {
  api
    .info()
    .then(() => {
      try {
        localStorage.setItem('steward.kiosk.paired', '1')
      } catch {
        /* storage unavailable */
      }
    })
    .catch(() => undefined)
})
function pair() {
  const code = pairCode.value.trim()
  if (code) window.location.href = `auth/terminal?code=${encodeURIComponent(code)}`
}

const productImage = (id: number) => productsById.value.get(id)?.image_url ?? null
const amountText = (c: Card) => formatAmount(total(c), c.unit)
const leftText = (c: Card) => {
  const left = inStock(c.productId)
  return left > 0 ? t.kiosk.left(formatAmount(left, c.unit)) : t.kiosk.noneLeft
}
</script>

<template>
  <div class="kiosk" :class="flash ? `kiosk--${flash}` : ''">
    <!-- Not paired (yet, or any more) -->
    <div v-if="auth.unpaired" class="kiosk__pair">
      <v-card variant="flat" border max-width="560" class="pa-6">
        <v-icon icon="mdi-monitor-dashboard" size="48" color="primary" class="mb-3" />
        <div class="text-h5 font-weight-bold mb-2">{{ t.kiosk.pairTitle }}</div>
        <v-alert v-if="wasPaired" type="warning" variant="tonal" density="compact" class="mb-3" :text="t.kiosk.removed" />
        <p class="text-body-1 text-medium-emphasis mb-5">{{ t.kiosk.pairText }}</p>
        <form class="d-flex ga-3" @submit.prevent="pair">
          <v-text-field
            v-model="pairCode"
            :label="t.kiosk.pairCode"
            placeholder="ABCD-EFGH"
            autofocus
            autocomplete="off"
            hide-details
            class="kiosk__code"
            @update:model-value="(v: string) => (pairCode = v.toUpperCase())"
          />
          <v-btn type="submit" color="primary" variant="flat" size="x-large" :disabled="!pairCode.trim()">{{ t.kiosk.pair }}</v-btn>
        </form>
      </v-card>
    </div>

    <template v-else>
      <v-sheet :color="style.color" class="kiosk__bar d-flex align-center px-4 ga-2">
        <div class="kiosk__clock mr-2">{{ clock.format(now) }}</div>
        <div class="d-flex flex-wrap ga-2 flex-grow-1">
          <v-btn
            v-for="m in MODES"
            :key="m"
            :variant="mode === m ? 'flat' : 'text'"
            :color="mode === m ? 'surface' : undefined"
            size="x-large"
            rounded="lg"
            :prepend-icon="STYLE[m].icon"
            class="kiosk__mode"
            :class="{ 'kiosk__mode--off': mode !== m }"
            @click="setMode(m)"
          >
            {{ t.kiosk.modes[m] }}
          </v-btn>
        </div>
        <v-icon :icon="connected ? 'mdi-circle' : 'mdi-circle-outline'" :color="connected ? 'white' : 'warning'" size="14" :title="connected ? t.app.live : t.kiosk.offline" />
      </v-sheet>

      <div class="kiosk__body">
        <section class="kiosk__main">
          <v-alert v-if="!connected" type="warning" variant="tonal" density="compact" class="mb-4" :text="t.kiosk.offline" />
          <v-alert
            v-else-if="message"
            :type="flash === 'error' || !flash ? 'info' : 'success'"
            variant="tonal"
            density="compact"
            class="mb-4"
            closable
            :text="message"
            @click:close="message = null"
          />

          <!-- Nothing in stock -->
          <v-card v-if="problem" variant="flat" border class="pa-6 mb-4 kiosk__problem">
            <div class="d-flex align-center ga-4">
              <v-icon icon="mdi-alert-circle-outline" size="56" color="error" />
              <div class="text-h5">{{ t.kiosk.notInStock(problem.name) }}</div>
            </div>
            <div class="d-flex flex-wrap ga-3 mt-5">
              <v-btn color="primary" variant="flat" size="x-large" prepend-icon="mdi-pencil" @click="correctAmount = 1; correcting = true">{{ t.kiosk.correct }}</v-btn>
              <v-btn variant="tonal" size="x-large" @click="problem = null">{{ t.kiosk.ignore }}</v-btn>
            </div>
          </v-card>

          <!-- The last scan -->
          <v-card v-else-if="current" :key="current.key" variant="flat" border class="pa-6 mb-4" :class="{ 'kiosk__card--undone': current.undone }">
            <div class="d-flex align-center ga-5">
              <v-avatar size="112" rounded="lg" :color="STYLE[current.mode].color" variant="tonal">
                <v-img v-if="productImage(current.productId)" :src="productImage(current.productId)!" cover />
                <span v-else class="text-h3 font-weight-bold">{{ current.name.charAt(0).toUpperCase() }}</span>
              </v-avatar>
              <div class="flex-grow-1" style="min-width: 0">
                <div class="text-h6 text-medium-emphasis d-flex align-center ga-2">
                  <v-icon :icon="STYLE[current.mode].icon" size="22" />
                  <template v-if="current.undone">{{ t.kiosk.undone }}</template>
                  <template v-else>{{ t.kiosk.did[current.mode] }} · {{ amountText(current) }}</template>
                  <v-chip v-if="current.bookings.length > 1" size="small" label :color="STYLE[current.mode].color">{{ t.kiosk.times(current.bookings.length) }}</v-chip>
                </div>
                <div class="text-h3 font-weight-bold kiosk__name">{{ current.name }}</div>
                <div class="d-flex flex-wrap align-center ga-2 mt-2">
                  <span class="text-h5">{{ leftText(current) }}</span>
                  <v-chip v-if="current.onList || stockById.get(current.productId)?.below_min" color="secondary" variant="tonal" prepend-icon="mdi-cart-outline" label>
                    {{ t.kiosk.onList }}
                  </v-chip>
                </div>
              </div>
            </div>
            <div v-if="!current.undone" class="d-flex flex-wrap align-center ga-3 mt-6">
              <v-btn icon="mdi-minus" size="x-large" variant="tonal" :aria-label="t.kiosk.less" :title="t.kiosk.less" @click="minus(current)" />
              <v-btn icon="mdi-plus" size="x-large" variant="tonal" :aria-label="t.kiosk.more" :title="t.kiosk.more" @click="plus(current)" />
              <v-btn v-if="current.mode === 'consume' && inStock(current.productId) > 0" size="x-large" variant="tonal" prepend-icon="mdi-check-all" @click="useAll(current)">
                {{ t.kiosk.useAll }}
              </v-btn>
              <v-spacer />
              <v-btn size="x-large" variant="text" prepend-icon="mdi-undo" @click="undoCard(current)">{{ t.kiosk.undo }}</v-btn>
            </div>
          </v-card>

          <!-- Waiting for a scan -->
          <div v-else class="kiosk__ready text-center py-10">
            <v-progress-circular v-if="busy" indeterminate size="72" :color="style.color" />
            <v-icon v-else icon="mdi-barcode-scan" size="96" :color="style.color" />
            <div class="text-h4 font-weight-bold mt-4">{{ t.kiosk.ready }}</div>
            <div class="text-h6 text-medium-emphasis">{{ t.kiosk.readyHint }}</div>
          </div>
          <div v-if="mode !== 'consume'" class="text-body-1 text-medium-emphasis mb-4">
            <v-icon icon="mdi-timer-sand" size="18" /> {{ t.kiosk.backSoon }}
          </div>

          <template v-if="earlier.length">
            <div class="text-overline text-medium-emphasis">{{ t.kiosk.earlier }}</div>
            <v-list class="bg-transparent py-0">
              <v-list-item v-for="c in earlier" :key="c.key" class="px-0" :class="{ 'kiosk__card--undone': c.undone }">
                <template #prepend>
                  <v-avatar :color="STYLE[c.mode].color" variant="tonal" size="40"><v-icon :icon="STYLE[c.mode].icon" size="20" /></v-avatar>
                </template>
                <v-list-item-title class="text-h6">{{ c.name }}</v-list-item-title>
                <v-list-item-subtitle>
                  {{ c.undone ? t.kiosk.undone : `${t.kiosk.did[c.mode]} · ${amountText(c)}` }} · {{ timeFmt.format(c.at) }}
                </v-list-item-subtitle>
                <template v-if="!c.undone" #append>
                  <v-btn variant="text" size="large" prepend-icon="mdi-undo" @click="undoCard(c)">{{ t.kiosk.undo }}</v-btn>
                </template>
              </v-list-item>
            </v-list>
          </template>
        </section>

        <aside class="kiosk__side">
          <v-autocomplete
            v-model="picked"
            v-model:search="search"
            :items="state.products"
            item-title="name"
            item-value="id"
            :placeholder="t.kiosk.search"
            prepend-inner-icon="mdi-magnify"
            variant="solo-filled"
            flat
            hide-details
            hide-no-data
            auto-select-first
            class="mb-4"
            @update:model-value="onPick"
          />
          <template v-if="frequent.length">
            <div class="text-overline text-medium-emphasis">{{ t.kiosk.frequent }}</div>
            <div class="kiosk__tiles">
              <v-btn
                v-for="p in frequent"
                :key="p.id"
                variant="tonal"
                :color="style.color"
                rounded="lg"
                height="96"
                stacked
                class="kiosk__tile"
                @click="bookProduct(p)"
              >
                <v-avatar v-if="p.image_url" size="40" rounded="lg" class="mb-1"><v-img :src="p.image_url" cover /></v-avatar>
                <span class="kiosk__tile-name">{{ p.name }}</span>
                <span class="text-caption text-medium-emphasis">{{ formatAmount(inStock(p.id), p.unit) }}</span>
              </v-btn>
            </div>
          </template>
        </aside>
      </div>
    </template>

    <!-- Unknown barcode: create or link the product, then the scan is booked -->
    <v-dialog :model-value="!!unknown" max-width="640" persistent>
      <ScanResultCard v-if="unknown" :result="unknown" mode="lookup" :stock="stockById" @done="unknownDone" @close="unknown = null" />
    </v-dialog>

    <v-dialog v-model="correcting" max-width="420">
      <v-card v-if="problem" :title="t.kiosk.correctTitle(problem.name)">
        <v-card-text>
          <v-text-field v-model="correctAmount" type="number" min="0" step="any" :suffix="problem.unit" autofocus hide-details @keydown.enter="saveCorrection" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="correcting = false">{{ t.common.cancel }}</v-btn>
          <v-btn color="primary" variant="flat" @click="saveCorrection">{{ t.common.save }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <div v-if="sleeping" class="kiosk__sleep" @pointerdown="activity">
      <div class="text-h6">{{ t.kiosk.wake }}</div>
    </div>
  </div>
</template>

<style scoped>
.kiosk {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  outline: 0 solid transparent;
  outline-offset: -12px;
  transition: outline-color 0.3s;
}
.kiosk--ok {
  outline: 12px solid rgb(var(--v-theme-success));
}
.kiosk--error {
  outline: 12px solid rgb(var(--v-theme-error));
}
.kiosk__bar {
  min-height: 76px;
  position: sticky;
  top: 0;
  z-index: 2;
}
.kiosk__clock {
  font-size: 1.75rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.kiosk__mode {
  font-size: 1.05rem;
  letter-spacing: 0;
}
/* Unselected modes take the bar's own text colour, whatever the mode colour is. */
.kiosk__mode--off {
  color: inherit !important;
}
.kiosk__body {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
  gap: 24px;
  padding: 24px;
  flex-grow: 1;
}
@media (max-width: 800px) {
  .kiosk__body {
    grid-template-columns: minmax(0, 1fr);
    padding: 16px;
  }
}
.kiosk__name {
  overflow-wrap: anywhere;
  line-height: 1.15;
}
.kiosk__card--undone {
  opacity: 0.5;
}
.kiosk__problem {
  border-color: rgb(var(--v-theme-error)) !important;
}
.kiosk__tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 10px;
}
.kiosk__tile {
  min-width: 0 !important;
  text-transform: none;
  letter-spacing: 0;
}
.kiosk__tile-name {
  font-size: 1rem;
  font-weight: 600;
  white-space: normal;
  line-height: 1.2;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.kiosk__pair {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.kiosk__code :deep(input) {
  font-size: 1.5rem;
  letter-spacing: 0.1em;
  font-family: ui-monospace, monospace;
}
.kiosk__sleep {
  position: fixed;
  inset: 0;
  z-index: 3000;
  background: #000;
  color: rgba(255, 255, 255, 0.35);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding-bottom: 48px;
  cursor: none;
}
</style>
