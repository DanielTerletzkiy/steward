<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { api, ApiError } from '@/api'
import { t } from '@/i18n'
import { kindIcon, stateLabel } from '@/composables/appliances'
import EmptyState from './EmptyState.vue'
import type { Equipment, HaDevice, HaEntity } from '@/types'

// Pick a Home Assistant device (to link) or a single entity (to add).
const open = defineModel<boolean>({ default: false })
const props = defineProps<{ mode: 'device' | 'entity'; equipment: Equipment; busy?: boolean }>()
const emit = defineEmits<{
  device: [{ device: HaDevice; kind: boolean; model: boolean }]
  entity: [HaEntity]
}>()
const { xs } = useDisplay()

const q = ref('')
const devices = shallowRef<HaDevice[]>([])
const entities = shallowRef<HaEntity[]>([])
const loading = ref(false)
const offline = ref(false)
const error = ref<string | null>(null)
const picked = ref<HaDevice | null>(null)
const takeKind = ref(true)
const takeModel = ref(true)

let timer: number | undefined
let seq = 0
async function search() {
  const mine = ++seq
  loading.value = true
  try {
    if (props.mode === 'device') devices.value = await api.haDevices(q.value.trim() || null)
    else entities.value = await api.haEntities(q.value.trim() || null)
    if (mine !== seq) return
    offline.value = false
    error.value = null
  } catch (e) {
    if (mine !== seq) return
    offline.value = e instanceof ApiError && e.status === 503
    error.value = offline.value ? null : e instanceof Error ? e.message : String(e)
  } finally {
    if (mine === seq) loading.value = false
  }
}
watch(open, (v) => {
  if (!v) return
  q.value = ''
  picked.value = null
  devices.value = []
  entities.value = []
  search()
})
watch(q, () => {
  window.clearTimeout(timer)
  timer = window.setTimeout(search, 300)
})
onBeforeUnmount(() => window.clearTimeout(timer))

const known = computed(() => new Set(props.equipment.ha_entities))
const modelText = (d: HaDevice) => [d.manufacturer, d.model].filter(Boolean).join(' · ')
const kindDiffers = computed(() => !!picked.value?.kind && picked.value.kind !== props.equipment.kind)
const modelDiffers = computed(() => {
  const d = picked.value
  return !!d && (!!d.manufacturer || !!d.model) && (d.manufacturer !== props.equipment.brand || d.model !== props.equipment.model)
})

function pickDevice(d: HaDevice) {
  picked.value = d
  takeKind.value = true
  takeModel.value = !props.equipment.brand && !props.equipment.model
}
function confirmDevice() {
  if (!picked.value) return
  emit('device', { device: picked.value, kind: kindDiffers.value && takeKind.value, model: modelDiffers.value && takeModel.value })
}
</script>

<template>
  <v-dialog v-model="open" :fullscreen="xs" max-width="600" scrollable>
    <v-card :rounded="xs ? 0 : 'xl'">
      <v-toolbar color="transparent" density="comfortable">
        <v-btn :icon="picked ? 'mdi-arrow-left' : 'mdi-close'" :title="picked ? t.common.back : t.common.close" @click="picked ? (picked = null) : (open = false)" />
        <v-toolbar-title class="font-weight-medium">{{ mode === 'device' ? t.appliances.pickDevice : t.appliances.pickEntity }}</v-toolbar-title>
      </v-toolbar>
      <div v-if="!picked" class="px-4 pb-2">
        <v-text-field
          v-model="q"
          :placeholder="mode === 'device' ? t.appliances.searchDevices : t.appliances.searchEntities"
          prepend-inner-icon="mdi-magnify"
          :loading="loading"
          clearable
          hide-details
          density="compact"
          variant="solo-filled"
          flat
          rounded="pill"
          autofocus
        />
      </div>
      <v-divider />
      <v-card-text class="pa-0" style="min-height: 280px">
        <!-- Confirm a device -->
        <div v-if="picked" class="pa-4">
          <div class="d-flex align-center mb-3">
            <v-avatar color="primary" variant="tonal" class="mr-3"><v-icon :icon="kindIcon[picked.kind ?? 'other']" /></v-avatar>
            <div class="min-w-0">
              <div class="text-subtitle-1 font-weight-medium">{{ picked.name }}</div>
              <div class="text-body-2 text-medium-emphasis">{{ [modelText(picked), picked.area].filter(Boolean).join(' · ') }}</div>
            </div>
          </div>
          <div class="d-flex flex-wrap ga-1 mb-4">
            <v-chip v-for="e in picked.entities" :key="e.entity_id" size="small" variant="outlined" label>{{ e.name || e.entity_id }}: {{ stateLabel(e.state) }}</v-chip>
          </div>
          <template v-if="kindDiffers || modelDiffers">
            <div class="text-subtitle-2 mb-1">{{ t.appliances.takeOver }}</div>
            <v-checkbox v-if="kindDiffers" v-model="takeKind" :label="t.appliances.useKind(t.appliances.kinds[picked.kind!] ?? picked.kind!)" density="compact" hide-details />
            <v-checkbox v-if="modelDiffers" v-model="takeModel" :label="t.appliances.useModel(modelText(picked))" density="compact" hide-details />
          </template>
        </div>

        <EmptyState v-else-if="offline" icon="mdi-home-off-outline" :title="t.appliances.haOffline" :text="t.appliances.haOfflineHint" />
        <v-alert v-else-if="error" type="error" variant="tonal" class="ma-4" :text="error" />

        <!-- Devices -->
        <template v-else-if="mode === 'device'">
          <EmptyState v-if="!loading && !devices.length" compact icon="mdi-devices" :title="t.appliances.noDevices" />
          <v-list v-else lines="three" bg-color="transparent">
            <v-list-item v-for="d in devices" :key="d.id" :active="d.id === equipment.ha_device_id" @click="pickDevice(d)">
              <template #prepend><v-avatar color="primary" variant="tonal"><v-icon :icon="kindIcon[d.kind ?? 'other']" /></v-avatar></template>
              <v-list-item-title class="font-weight-medium wrap">{{ d.name }}</v-list-item-title>
              <v-list-item-subtitle>{{ [modelText(d), d.area].filter(Boolean).join(' · ') }}</v-list-item-subtitle>
              <div class="d-flex flex-wrap ga-1 mt-1">
                <v-chip v-for="e in d.entities.slice(0, 3)" :key="e.entity_id" size="x-small" variant="outlined" label>{{ e.name || e.entity_id }}</v-chip>
                <v-chip v-if="d.entities.length > 3" size="x-small" variant="text" label>{{ t.appliances.moreEntities(d.entities.length - 3) }}</v-chip>
              </div>
            </v-list-item>
          </v-list>
        </template>

        <!-- Entities -->
        <template v-else>
          <EmptyState v-if="!loading && !entities.length" compact icon="mdi-shape-outline" :title="t.appliances.noEntities" />
          <v-list v-else lines="two" bg-color="transparent">
            <v-list-item v-for="e in entities" :key="e.entity_id" :disabled="known.has(e.entity_id) || busy" @click="emit('entity', e)">
              <v-list-item-title class="font-weight-medium">{{ e.name || e.entity_id }}</v-list-item-title>
              <v-list-item-subtitle>{{ e.entity_id }} · {{ stateLabel(e.state) }}</v-list-item-subtitle>
              <template #append><v-icon :icon="known.has(e.entity_id) ? 'mdi-check' : 'mdi-plus'" /></template>
            </v-list-item>
          </v-list>
        </template>
      </v-card-text>
      <template v-if="picked">
        <v-divider />
        <v-card-actions class="px-4">
          <v-spacer />
          <v-btn @click="picked = null">{{ t.common.back }}</v-btn>
          <v-btn color="primary" variant="flat" prepend-icon="mdi-link-variant" :loading="busy" @click="confirmDevice">{{ t.appliances.link }}</v-btn>
        </v-card-actions>
      </template>
    </v-card>
  </v-dialog>
</template>
