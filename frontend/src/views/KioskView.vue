<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/api'
import { LOCALE, t } from '@/i18n'
import { auth } from '@/composables/auth'
import { connected, serverVersion } from '@/composables/live'
import { useResource } from '@/composables/resource'
import { useCatalog } from '@/composables/catalog'
import { useWedgeScanner } from '@/composables/barcode'
import { formatAmount } from '@/composables/format'
import { createKiosk, MODE_STYLE, MODES, provideKiosk, type KioskTab } from '@/composables/kiosk'
import ScanResultCard from '@/components/ScanResultCard.vue'
import PhotoScan from '@/components/PhotoScan.vue'
import KioskScan from '@/components/kiosk/KioskScan.vue'
import KioskStock from '@/components/kiosk/KioskStock.vue'
import KioskChores from '@/components/kiosk/KioskChores.vue'
import KioskRecipes from '@/components/kiosk/KioskRecipes.vue'
import KioskTerminal from '@/components/kiosk/KioskTerminal.vue'
import { appCall, inApp } from '@/composables/kioskApp'
import type { StockItem } from '@/types'

// The kitchen terminal: a full-screen page for a fixed screen with a barcode scanner (and maybe a
// camera). Tabs on the left, the scan mode on top; scanning works on every tab.
const IDLE_MS = 5 * 60_000 // then the page goes dark, unless a recipe is open
const KEY_STORE = 'steward.kiosk.key'
const RESTORE_GUARD = 'steward.kiosk.restoredAt'

const route = useRoute()
const router = useRouter()
const { productsById } = useCatalog()
const { data: stock } = useResource<StockItem[]>(() => api.stock(true), ['stock', 'catalog'], [])
const stockById = computed(() => new Map(stock.value.map((s) => [s.product.id, s])))

const kiosk = createKiosk(stockById, productsById)
provideKiosk(kiosk)
const { mode, tab, flash } = kiosk

const TABS: { value: KioskTab; icon: string }[] = [
  { value: 'scan', icon: 'mdi-barcode-scan' },
  { value: 'stock', icon: 'mdi-fridge-outline' },
  { value: 'recipes', icon: 'mdi-chef-hat' },
  { value: 'photo', icon: 'mdi-camera-outline' },
]
const terminalOpen = ref(false)

// --- clock, idle, keeping the screen on ------------------------------------------------

const now = ref(Date.now())
let lastActive = Date.now()
const sleeping = ref(false)
const clock = new Intl.DateTimeFormat(LOCALE, { hour: '2-digit', minute: '2-digit' })
function activity() {
  lastActive = Date.now()
  sleeping.value = false
}

// In the Steward Kiosk app, the dark page also switches the display off (unless that is turned off in
// the app's settings), and any key, scan or touch switches it on again.
if (inApp) {
  appCall('set_screen', { idle: false }).catch(() => undefined)
  watch(sleeping, (idle) => appCall('set_screen', { idle }).catch(() => undefined))
}

// The mouse pointer only shows while the mouse moves (dialogs included, so on the whole document).
let pointerTimer: number | undefined
const hidePointer = (hide: boolean) => document.documentElement.classList.toggle('kiosk-no-pointer', hide)
function pointerMoved(e: PointerEvent) {
  if (e.pointerType !== 'mouse') return
  hidePointer(false)
  window.clearTimeout(pointerTimer)
  pointerTimer = window.setTimeout(() => hidePointer(true), 3000)
}

// In a browser, the wake lock keeps the screen from blanking while cooking (it needs a secure page).
let wakeLock: WakeLockSentinel | null = null
async function holdScreen(on: boolean) {
  if (on && !wakeLock && 'wakeLock' in navigator && document.visibilityState === 'visible') {
    wakeLock = await navigator.wakeLock.request('screen').catch(() => null)
    wakeLock?.addEventListener('release', () => (wakeLock = null))
  } else if (!on && wakeLock) {
    await wakeLock.release().catch(() => undefined)
    wakeLock = null
  }
}
watch(kiosk.keepAwake, holdScreen)
const onVisible = () => holdScreen(kiosk.keepAwake.value)

// Typing anywhere goes into the active tab's field, without clicking into it first.
function typeAnywhere(e: KeyboardEvent) {
  if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || e.key.length !== 1) return
  const active = document.activeElement as HTMLElement | null
  if (active && (active.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(active.tagName))) return
  const target = kiosk.focusTarget.value
  if (!target || document.querySelector('.v-overlay--active')) return
  e.preventDefault()
  target.focus()
  target.value += e.key
  target.dispatchEvent(new Event('input', { bubbles: true }))
}

let ticker: number | undefined
onMounted(() => {
  ticker = window.setInterval(() => {
    now.value = Date.now()
    kiosk.tick(now.value)
    if (kiosk.keepAwake.value) lastActive = now.value
    else if (!sleeping.value && now.value - lastActive > IDLE_MS) sleeping.value = true
  }, 1000)
  window.addEventListener('keydown', activity, true)
  window.addEventListener('pointerdown', activity, true)
  window.addEventListener('keydown', typeAnywhere)
  window.addEventListener('pointermove', pointerMoved)
  hidePointer(true)
  document.addEventListener('visibilitychange', onVisible)
})
onBeforeUnmount(() => {
  window.clearInterval(ticker)
  window.removeEventListener('keydown', activity, true)
  window.removeEventListener('pointerdown', activity, true)
  window.removeEventListener('keydown', typeAnywhere)
  window.removeEventListener('pointermove', pointerMoved)
  window.clearTimeout(pointerTimer)
  hidePointer(false)
  document.removeEventListener('visibilitychange', onVisible)
  holdScreen(false)
})

// Not on the pairing screen: a code typed quickly there would look like a scan.
useWedgeScanner(kiosk.onScan, { inFields: true, enabled: () => !auth.unpaired })

// Nobody reloads a kiosk: after Steward was updated, load the new version by itself.
watch(serverVersion, (now, before) => {
  if (before && now && now !== before) window.location.reload()
})

// --- staying paired -------------------------------------------------------------------
// The terminal keeps its key in local storage (and the Steward Kiosk app keeps it on the Pi), so a
// browser that loses its cookie signs in again by itself. Only removing the terminal in Settings ends that.

function keepKey(key: string) {
  storage.set(KEY_STORE, key)
  if (inApp) appCall('remember_key', { key }).catch(() => undefined)
}

const storage = {
  get: (k: string, s: Storage = localStorage) => {
    try {
      return s.getItem(k)
    } catch {
      return null
    }
  },
  set: (k: string, v: string | null, s: Storage = localStorage) => {
    try {
      if (v == null) s.removeItem(k)
      else s.setItem(k, v)
    } catch {
      /* storage unavailable */
    }
  },
}
const restoring = ref(false)
const removed = ref(false)
const cookiesBlocked = ref(false)

// The key from the address (the app, or a pairing link) is kept at once: the first requests, made
// while this page was still loading, may already have found the cookie missing.
const keyFromUrl = typeof route.query.key === 'string' ? route.query.key : null
if (keyFromUrl) keepKey(keyFromUrl)

onMounted(async () => {
  if (keyFromUrl) {
    router.replace({ path: '/kiosk' })
  } else if (!storage.get(KEY_STORE)) {
    // Paired before 0.4.0: the cookie still works, so keep its key from now on.
    const res = await fetch('auth/terminal/key', { credentials: 'same-origin' }).catch(() => null)
    if (res?.ok) keepKey((await res.json()).key)
  }
  restore()
})

async function restore() {
  if (!auth.unpaired || restoring.value) return
  const key = storage.get(KEY_STORE)
  if (!key) return
  // Signed in again a moment ago and lost it at once: if the key still works, the browser drops cookies.
  const justRestored = Date.now() - Number(storage.get(RESTORE_GUARD, sessionStorage) ?? 0) < 20_000
  restoring.value = true
  try {
    const res = await fetch('auth/terminal/session', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key }),
    })
    if (res.status === 401) {
      storage.set(KEY_STORE, null)
      if (inApp) appCall('forget_key').catch(() => undefined)
      removed.value = true
    } else if (res.ok && justRestored) {
      cookiesBlocked.value = true
    } else if (res.ok) {
      storage.set(RESTORE_GUARD, String(Date.now()), sessionStorage)
      window.location.reload()
      return
    }
  } catch {
    window.setTimeout(restore, 10_000) // Steward unreachable: try again
  }
  restoring.value = false
}
watch(() => auth.unpaired, restore, { immediate: true })

const pairCode = ref('')
function pair() {
  const code = pairCode.value.trim()
  if (code) window.location.href = `auth/terminal?code=${encodeURIComponent(code)}`
}

// --- outside the scan tab, a booking shows as a banner -------------------------------------

const showBanner = computed(() => tab.value !== 'scan' && now.value < kiosk.bannerUntil.value)
const banner = computed(() => {
  const c = kiosk.current.value
  if (kiosk.problem.value || flash.value === 'error' || !c) return { text: kiosk.message.value ?? t.kiosk.failed, card: null }
  if (kiosk.message.value) return { text: kiosk.message.value, card: null }
  return { text: `${t.kiosk.did[c.mode]} · ${formatAmount(kiosk.total(c), c.unit)} ${c.name}`, card: c }
})
watch(tab, () => (kiosk.bannerUntil.value = 0))
</script>

<template>
  <div class="kiosk" :class="flash ? `kiosk--${flash}` : ''">
    <!-- Not paired (yet, or any more) -->
    <div v-if="auth.unpaired" class="kiosk__pair">
      <v-progress-circular v-if="restoring" indeterminate size="64" color="primary" />
      <v-card v-else variant="flat" border max-width="560" class="pa-6">
        <v-icon icon="mdi-monitor-dashboard" size="48" color="primary" class="mb-3" />
        <div class="text-h5 font-weight-bold mb-2">{{ t.kiosk.pairTitle }}</div>
        <v-alert v-if="removed" type="warning" variant="tonal" density="compact" class="mb-3" :text="t.kiosk.removed" />
        <v-alert v-if="cookiesBlocked" type="error" variant="tonal" density="compact" class="mb-3" :text="t.kiosk.cookiesBlocked" />
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
      <v-sheet :color="kiosk.style.value.color" class="kiosk__bar d-flex align-center px-4 ga-2">
        <div class="kiosk__clock mr-2">{{ clock.format(now) }}</div>
        <div class="d-flex flex-wrap ga-2 flex-grow-1">
          <v-btn
            v-for="m in MODES"
            :key="m"
            :variant="mode === m ? 'flat' : 'text'"
            :color="mode === m ? 'surface' : undefined"
            size="x-large"
            rounded="lg"
            :prepend-icon="MODE_STYLE[m].icon"
            class="kiosk__mode"
            :class="{ 'kiosk__mode--off': mode !== m }"
            @click="kiosk.setMode(m)"
          >
            {{ t.kiosk.modes[m] }}
          </v-btn>
        </div>
        <!-- Only when the live connection to Steward is lost; while connected there is nothing to show. -->
        <v-chip v-if="!connected" color="warning" variant="flat" size="large" prepend-icon="mdi-wifi-off" :title="t.kiosk.offline">{{ t.app.offlineShort }}</v-chip>
      </v-sheet>

      <div class="kiosk__frame">
        <nav class="kiosk__rail">
          <v-btn
            v-for="item in TABS"
            :key="item.value"
            :variant="tab === item.value ? 'tonal' : 'text'"
            :color="tab === item.value ? 'primary' : undefined"
            stacked
            rounded="lg"
            height="84"
            class="kiosk__rail-btn"
            :prepend-icon="item.icon"
            @click="tab = item.value"
          >
            {{ t.kiosk.tabs[item.value] }}
          </v-btn>
          <v-spacer />
          <v-btn v-if="inApp" variant="text" stacked rounded="lg" height="84" class="kiosk__rail-btn" prepend-icon="mdi-cog-outline" @click="terminalOpen = true">
            {{ t.kiosk.terminal.title }}
          </v-btn>
        </nav>

        <main class="kiosk__body">
          <v-alert v-if="!connected" type="warning" variant="tonal" density="compact" class="mb-4" :text="t.kiosk.offline" />
          <v-alert
            v-else-if="showBanner"
            :type="flash === 'error' || kiosk.problem.value ? 'error' : 'success'"
            variant="tonal"
            class="mb-4"
            :text="banner.text"
          >
            <template #append>
              <v-btn v-if="banner.card && !banner.card.undone" variant="text" size="large" prepend-icon="mdi-undo" @click="kiosk.undoCard(banner.card)">{{ t.kiosk.undo }}</v-btn>
              <v-btn v-if="kiosk.problem.value" variant="text" size="large" @click="tab = 'scan'">{{ t.kiosk.show }}</v-btn>
            </template>
          </v-alert>
          <v-alert
            v-else-if="tab === 'scan' && kiosk.message.value && !kiosk.problem.value"
            :type="flash === 'error' ? 'error' : 'info'"
            variant="tonal"
            density="compact"
            class="mb-4"
            closable
            :text="kiosk.message.value"
            @click:close="kiosk.message.value = null"
          />

          <KioskScan v-if="tab === 'scan'" :stock-by-id="stockById" />
          <div v-else-if="tab === 'stock'" class="kiosk__split">
            <KioskStock :stock="stock" />
            <KioskChores />
          </div>
          <KioskRecipes v-else-if="tab === 'recipes'" />
          <PhotoScan v-else-if="tab === 'photo'" large />
        </main>
      </div>
    </template>

    <!-- Unknown barcode: create or link the product, then the scan is booked -->
    <v-dialog :model-value="!!kiosk.unknown.value" max-width="640" persistent>
      <ScanResultCard v-if="kiosk.unknown.value" :result="kiosk.unknown.value" mode="lookup" :stock="stockById" @done="kiosk.unknownDone()" @close="kiosk.unknown.value = null" />
    </v-dialog>

    <v-dialog v-model="terminalOpen" max-width="640" scrollable>
      <v-card :title="t.kiosk.terminal.title">
        <v-card-text><KioskTerminal v-if="terminalOpen" /></v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn size="large" @click="terminalOpen = false">{{ t.common.close }}</v-btn>
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
.kiosk__frame {
  display: flex;
  flex-grow: 1;
  min-height: 0;
}
.kiosk__rail {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 8px;
  width: 112px;
  flex-shrink: 0;
  border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  position: sticky;
  top: 76px;
  height: calc(100vh - 76px);
}
.kiosk__rail-btn {
  letter-spacing: 0;
  font-size: 0.95rem;
}
.kiosk__body {
  flex-grow: 1;
  min-width: 0;
  padding: 24px;
}
.kiosk__split {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
  gap: 24px;
  align-items: start;
}
@media (max-width: 900px) {
  .kiosk__split {
    grid-template-columns: minmax(0, 1fr);
  }
  .kiosk__rail {
    width: 84px;
  }
  .kiosk__body {
    padding: 16px;
  }
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

<style>
html.kiosk-no-pointer,
html.kiosk-no-pointer * {
  cursor: none !important;
}
</style>
