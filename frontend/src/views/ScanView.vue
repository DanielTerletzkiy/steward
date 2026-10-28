<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '@/api'
import { LOCALE, t } from '@/i18n'
import { useResource } from '@/composables/resource'
import { formatAmount } from '@/composables/format'
import { useWedgeScanner } from '@/composables/barcode'
import { modeIcon, SCAN_MODES, scanLog, type LogEntry } from '@/composables/scanActions'
import ScanCamera from '@/components/ScanCamera.vue'
import ScanResultCard from '@/components/ScanResultCard.vue'
import PhotoScan from '@/components/PhotoScan.vue'
import EmptyState from '@/components/EmptyState.vue'
import type { ScanLookup, ScanMode, StockItem } from '@/types'

function load<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(`steward.scan.${key}`)
    return v ? (JSON.parse(v) as T) : fallback
  } catch {
    return fallback
  }
}
const mode = ref<ScanMode>(load('mode', 'purchase'))
const tab = ref<'barcode' | 'photo'>(load('tab', 'barcode'))
watch([mode, tab], () => {
  try {
    localStorage.setItem('steward.scan.mode', JSON.stringify(mode.value))
    localStorage.setItem('steward.scan.tab', JSON.stringify(tab.value))
  } catch {
    /* storage unavailable */
  }
})

const { data: stock } = useResource<StockItem[]>(() => api.stock(true), ['stock', 'catalog'], [])
const stockById = computed(() => new Map(stock.value.map((s) => [s.product.id, s])))

const manual = ref('')
const looking = ref(false)
const result = ref<ScanLookup | null>(null)
const error = ref<string | null>(null)

async function lookup(code: string) {
  const c = code.trim()
  if (!c) return
  looking.value = true
  error.value = null
  try {
    result.value = await api.scanLookup(c)
    manual.value = ''
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    looking.value = false
  }
}
useWedgeScanner((code) => {
  if (tab.value === 'barcode') lookup(code)
})

const timeFmt = new Intl.DateTimeFormat(LOCALE, { hour: '2-digit', minute: '2-digit' })
async function undo(e: LogEntry) {
  if (!e.undo || e.undone) return
  await e.undo()
  e.undone = true
}
</script>

<template>
  <div class="page">
    <div class="d-flex align-center mb-3">
      <div class="page-title">{{ t.scan.title }}</div>
      <v-spacer />
      <v-btn-toggle v-model="tab" mandatory density="compact" rounded="pill" variant="outlined" divided color="primary">
        <v-btn value="barcode" prepend-icon="mdi-barcode">{{ t.scan.barcode }}</v-btn>
        <v-btn value="photo" prepend-icon="mdi-camera-outline">{{ t.scan.photo }}</v-btn>
      </v-btn-toggle>
    </div>

    <template v-if="tab === 'barcode'">
      <v-chip-group v-model="mode" mandatory selected-class="text-primary" class="mb-3">
        <v-chip v-for="m in SCAN_MODES" :key="m" :value="m" :prepend-icon="modeIcon[m]" variant="outlined" size="default" filter>{{ t.scan.modes[m] }}</v-chip>
      </v-chip-group>

      <v-row>
        <v-col cols="12" md="6">
          <ScanCamera class="mb-3" @detected="lookup" />
          <v-form @submit.prevent="lookup(manual)">
            <v-text-field
              v-model="manual"
              :label="t.scan.manual"
              :placeholder="t.scan.manualPlaceholder"
              prepend-inner-icon="mdi-barcode"
              inputmode="numeric"
              autocomplete="off"
              :loading="looking"
              hide-details
            >
              <template #append-inner>
                <v-btn v-if="manual.trim()" color="primary" variant="flat" size="small" :loading="looking" @click="lookup(manual)">{{ t.scan.look }}</v-btn>
              </template>
            </v-text-field>
          </v-form>
          <div class="text-caption text-medium-emphasis mt-2 d-flex align-center"><v-icon icon="mdi-keyboard-outline" size="14" class="mr-1" />{{ t.scan.scannerHint }}</div>
        </v-col>

        <v-col cols="12" md="6">
          <v-alert v-if="error" type="error" variant="tonal" :text="error" class="mb-3" closable @click:close="error = null" />
          <v-progress-linear v-if="looking" indeterminate color="primary" rounded class="mb-3" />
          <ScanResultCard v-if="result" :result="result" :mode="mode" :stock="stockById" class="mb-4" @done="result = null" @close="result = null" />

          <v-card variant="flat" border>
            <v-card-item prepend-icon="mdi-history">
              <v-card-title class="text-subtitle-1 font-weight-medium">{{ t.scan.log }}</v-card-title>
            </v-card-item>
            <EmptyState v-if="!scanLog.length" compact icon="mdi-barcode-scan" :title="t.scan.logEmpty" />
            <v-list v-else density="comfortable" bg-color="transparent">
              <v-list-item v-for="e in scanLog" :key="e.id" :class="{ 'opacity-60': e.undone }">
                <template #prepend><v-avatar color="primary" variant="tonal" size="36"><v-icon :icon="modeIcon[e.mode]" size="18" /></v-avatar></template>
                <v-list-item-title :class="{ 'line-through': e.undone }">{{ e.name }}</v-list-item-title>
                <v-list-item-subtitle>{{ t.scan.modes[e.mode] }} · {{ formatAmount(e.amount, e.unit) }} · {{ timeFmt.format(e.at) }}</v-list-item-subtitle>
                <template #append>
                  <v-chip v-if="e.undone" size="x-small" variant="tonal" label>{{ t.scan.undone }}</v-chip>
                  <v-btn v-else-if="e.undo" variant="text" size="small" prepend-icon="mdi-undo" @click="undo(e)">{{ t.scan.undo }}</v-btn>
                </template>
              </v-list-item>
            </v-list>
          </v-card>
        </v-col>
      </v-row>
    </template>

    <v-row v-else>
      <v-col cols="12" lg="8"><PhotoScan /></v-col>
    </v-row>
  </div>
</template>
