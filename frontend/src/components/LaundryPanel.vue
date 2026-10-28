<script setup lang="ts">
import { computed, ref } from 'vue'
import { LOCALE, t } from '@/i18n'
import { daysFromToday, formatTime, parseDateTime, relativeDay } from '@/composables/format'
import { laundryDone, markDry, startWash, stillFine, toLaundry } from '@/composables/wardrobe'
import GarmentThumb from './GarmentThumb.vue'
import type { Garment } from '@/types'

// The laundry cycle at a glance: ready for the wash → laundry bin → in the wash → drying → clean.
const props = defineProps<{ garments: Garment[]; hasWasher: boolean }>()
const emit = defineEmits<{ open: [Garment] }>()

const byName = (a: Garment, b: Garment) => a.name.localeCompare(b.name, LOCALE)
const ready = computed(() => props.garments.filter((g) => g.needs_wash && !['laundry', 'washing', 'drying'].includes(g.state)).sort(byName))
const bin = computed(() => props.garments.filter((g) => g.state === 'laundry').sort(byName))
const washing = computed(() => props.garments.filter((g) => g.state === 'washing').sort(byName))
const drying = computed(() =>
  props.garments.filter((g) => g.state === 'drying').sort((a, b) => (a.dry_until ?? '9999').localeCompare(b.dry_until ?? '9999') || byName(a, b)),
)
const anything = computed(() => ready.value.length + bin.value.length + washing.value.length + drying.value.length > 0)

const summary = computed(() => {
  const parts: string[] = []
  if (ready.value.length) parts.push(t.today.needsWashCount(ready.value.length))
  if (bin.value.length) parts.push(t.wardrobe.inLaundry(bin.value.length))
  if (washing.value.length) parts.push(t.today.washingCount(washing.value.length))
  if (drying.value.length) parts.push(t.today.dryingCount(drying.value.length))
  return parts.join(' · ') || t.wardrobe.allClean
})

const LIMIT = 4
const expanded = ref<Record<string, boolean>>({})
const shown = (key: string, list: Garment[]) => (expanded.value[key] ? list : list.slice(0, LIMIT))

function dryText(g: Garment) {
  if (!g.dry_until) return t.wardrobe.dryManual
  const d = parseDateTime(g.dry_until)
  return t.wardrobe.dryUntil(`${relativeDay(daysFromToday(d))} ${formatTime(g.dry_until)}`)
}

const busy = ref<string | null>(null)
async function run(key: string, fn: () => Promise<boolean>) {
  busy.value = key
  await fn()
  busy.value = null
}
</script>

<template>
  <v-card variant="flat" border class="h-100">
    <v-card-item>
      <template #prepend>
        <v-avatar :color="anything ? 'warning' : 'success'" variant="tonal"><v-icon :icon="anything ? 'mdi-washing-machine' : 'mdi-check-all'" /></v-avatar>
      </template>
      <v-card-title class="text-subtitle-1 font-weight-medium">{{ t.wardrobe.laundry }}</v-card-title>
      <v-card-subtitle class="text-wrap">{{ summary }}</v-card-subtitle>
    </v-card-item>

    <!-- Ready for the wash? -->
    <template v-if="ready.length">
      <v-divider />
      <div class="section">
        <div class="d-flex align-center mb-1">
          <div class="min-w-0">
            <div class="text-subtitle-2">{{ t.wardrobe.readyForWash }}</div>
            <div class="text-caption text-medium-emphasis">{{ t.wardrobe.readyHint }}</div>
          </div>
          <v-spacer />
          <v-btn v-if="ready.length > 1" size="small" variant="text" color="primary" :loading="busy === 'ready-all'" @click="run('ready-all', () => toLaundry(ready))">{{ t.wardrobe.allToLaundry }}</v-btn>
        </div>
        <div v-for="g in shown('ready', ready)" :key="g.id" class="d-flex align-center ga-2 py-1">
          <div class="thumb clickable" @click="emit('open', g)"><GarmentThumb :photo-id="g.photo_id" :layer="g.layer" :icon-size="16" rounded="md" /></div>
          <div class="text-body-2 text-truncate flex-grow-1 clickable" @click="emit('open', g)">{{ g.name }}</div>
          <v-btn size="small" variant="text" :disabled="!!busy" @click="run(`fine-${g.id}`, () => stillFine([g]))">{{ t.wardrobe.stillFine }}</v-btn>
          <v-btn size="small" variant="tonal" color="primary" icon="mdi-basket-plus-outline" :title="t.wardrobe.toLaundry" :loading="busy === `add-${g.id}`" :disabled="!!busy" @click="run(`add-${g.id}`, () => toLaundry([g]))" />
        </div>
        <v-btn v-if="ready.length > LIMIT" size="x-small" variant="text" @click="expanded.ready = !expanded.ready">
          {{ expanded.ready ? t.wardrobe.showLess : t.wardrobe.moreN(ready.length - LIMIT) }}
        </v-btn>
      </div>
    </template>

    <!-- Laundry bin -->
    <template v-if="bin.length">
      <v-divider />
      <div class="section">
        <div class="text-subtitle-2 mb-2">{{ t.wardrobe.laundryBin }} <span class="text-medium-emphasis">{{ bin.length }}</span></div>
        <div class="d-flex flex-wrap ga-1 mb-2">
          <div v-for="g in bin.slice(0, 10)" :key="g.id" class="thumb clickable" :title="g.name" @click="emit('open', g)">
            <GarmentThumb :photo-id="g.photo_id" :layer="g.layer" :icon-size="16" rounded="md" />
          </div>
          <span v-if="bin.length > 10" class="text-caption text-medium-emphasis align-self-center ml-1">{{ t.wardrobe.moreN(bin.length - 10) }}</span>
        </div>
        <div class="d-flex flex-wrap ga-2">
          <v-btn v-if="!hasWasher" size="small" variant="tonal" prepend-icon="mdi-washing-machine" :loading="busy === 'start'" :disabled="!!busy" @click="run('start', () => startWash(bin))">
            {{ t.wardrobe.startedWasher }}
          </v-btn>
          <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-check" :loading="busy === 'bin-done'" :disabled="!!busy" @click="run('bin-done', () => laundryDone(bin))">
            {{ t.wardrobe.washed }}
          </v-btn>
        </div>
      </div>
    </template>

    <!-- In the washer -->
    <template v-if="washing.length">
      <v-divider />
      <div class="section">
        <div class="d-flex align-center mb-2">
          <div class="text-subtitle-2">{{ t.wardrobe.inTheWash }} <span class="text-medium-emphasis">{{ washing.length }}</span></div>
          <v-progress-circular indeterminate size="14" width="2" color="primary" class="ml-2" />
        </div>
        <div class="d-flex flex-wrap ga-1 mb-2">
          <div v-for="g in washing.slice(0, 10)" :key="g.id" class="thumb clickable" :title="g.name" @click="emit('open', g)">
            <GarmentThumb :photo-id="g.photo_id" :layer="g.layer" :icon-size="16" rounded="md" />
          </div>
          <span v-if="washing.length > 10" class="text-caption text-medium-emphasis align-self-center ml-1">{{ t.wardrobe.moreN(washing.length - 10) }}</span>
        </div>
        <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-check" :loading="busy === 'wash-done'" :disabled="!!busy" @click="run('wash-done', () => laundryDone(washing))">
          {{ t.wardrobe.washed }}
        </v-btn>
      </div>
    </template>

    <!-- Drying -->
    <template v-if="drying.length">
      <v-divider />
      <div class="section">
        <div class="d-flex align-center mb-1">
          <div class="text-subtitle-2">{{ t.wardrobe.drying }} <span class="text-medium-emphasis">{{ drying.length }}</span></div>
          <v-spacer />
          <v-btn v-if="drying.length > 1" size="small" variant="text" color="primary" :loading="busy === 'dry-all'" :disabled="!!busy" @click="run('dry-all', () => markDry(drying))">{{ t.wardrobe.allDry }}</v-btn>
        </div>
        <div v-for="g in shown('drying', drying)" :key="g.id" class="d-flex align-center ga-2 py-1">
          <div class="thumb clickable" @click="emit('open', g)"><GarmentThumb :photo-id="g.photo_id" :layer="g.layer" :icon-size="16" rounded="md" /></div>
          <div class="min-w-0 flex-grow-1 clickable" @click="emit('open', g)">
            <div class="text-body-2 text-truncate">{{ g.name }}</div>
            <div class="text-caption text-medium-emphasis text-truncate">{{ dryText(g) }}</div>
          </div>
          <v-btn size="small" variant="tonal" prepend-icon="mdi-weather-sunny" :loading="busy === `dry-${g.id}`" :disabled="!!busy" @click="run(`dry-${g.id}`, () => markDry([g]))">{{ t.wardrobe.dryNow }}</v-btn>
        </div>
        <v-btn v-if="drying.length > LIMIT" size="x-small" variant="text" @click="expanded.drying = !expanded.drying">
          {{ expanded.drying ? t.wardrobe.showLess : t.wardrobe.moreN(drying.length - LIMIT) }}
        </v-btn>
      </div>
    </template>
  </v-card>
</template>

<style scoped>
.section {
  padding: 12px 16px;
}
.thumb {
  width: 36px;
  flex: none;
}
</style>
