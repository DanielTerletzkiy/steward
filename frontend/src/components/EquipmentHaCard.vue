<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { attempt, notify } from '@/composables/notify'
import { AUTOMATION_DEFAULTS, isLinked, kindIcon, KINDS } from '@/composables/appliances'
import HaPickerDialog from './HaPickerDialog.vue'
import ConfirmDialog from './ConfirmDialog.vue'
import type { Equipment, EquipmentIn, HaDevice, HaEntity } from '@/types'

// The "Home Assistant" section of a device: link, kind and what happens when a run finishes.
const props = defineProps<{ equipment: Equipment }>()
const emit = defineEmits<{ updated: [Equipment] }>()

const busy = ref(false)
async function save(body: Partial<EquipmentIn> & { ha_device_id?: string | null }, msg?: string) {
  busy.value = true
  const res = await attempt(() => api.updateEquipment(props.equipment.id, body as Partial<EquipmentIn>))
  busy.value = false
  if (res) {
    emit('updated', res)
    if (msg) notify(msg)
  }
  return !!res
}

// Show the linked device's name when Home Assistant can tell us (it may be offline).
const device = ref<HaDevice | null>(null)
watch(
  () => props.equipment.ha_device_id,
  async (id) => {
    device.value = null
    if (!id) return
    try {
      device.value = (await api.haDevices()).find((d) => d.id === id) ?? null
    } catch {
      /* offline: show the id */
    }
  },
  { immediate: true },
)

const pickerOpen = ref(false)
const pickerMode = ref<'device' | 'entity'>('device')
function openPicker(mode: 'device' | 'entity') {
  pickerMode.value = mode
  pickerOpen.value = true
}
async function linkDevice(sel: { device: HaDevice; kind: boolean; model: boolean }) {
  const body: Partial<EquipmentIn> & { ha_device_id?: string | null } = { ha_device_id: sel.device.id }
  if (sel.kind && sel.device.kind) body.kind = sel.device.kind
  if (sel.model) {
    body.brand = sel.device.manufacturer
    body.model = sel.device.model
  }
  if (await save(body, t.appliances.linked)) pickerOpen.value = false
}
async function addEntity(e: HaEntity) {
  if (await save({ ha_entities: [...props.equipment.ha_entities, e.entity_id] }, t.appliances.linked)) pickerOpen.value = false
}
async function removeEntity(id: string) {
  await save({ ha_entities: props.equipment.ha_entities.filter((x) => x !== id) })
}
const confirmUnlink = ref(false)
async function unlink() {
  await save({ ha_device_id: null, ha_entities: [] }, t.appliances.unlinked)
}

// --- kind and automation
const kindItems = KINDS.map((k) => ({ value: k, title: t.appliances.kinds[k], icon: kindIcon[k] }))
const defaults = computed(() => AUTOMATION_DEFAULTS[props.equipment.kind] ?? AUTOMATION_DEFAULTS.other)
const choreItems = computed(() => [
  { value: '__default', title: t.appliances.byDefault(t.appliances.chores[defaults.value.chores]) },
  ...(['complete', 'make_due', 'off'] as const).map((v) => ({ value: v, title: t.appliances.chores[v] })),
])
const isDryer = computed(() => props.equipment.kind === 'dryer')
const laundryLabel = (v: string) => (isDryer.value ? t.appliances.dryerModes[v] : t.appliances.laundryModes[v]) ?? v
const laundryItems = computed(() => [
  { value: '__default', title: t.appliances.byDefault(laundryLabel(defaults.value.laundry)) },
  ...(isDryer.value ? (['auto', 'off'] as const) : (['auto', 'ask', 'off'] as const)).map((v) => ({ value: v, title: laundryLabel(v) })),
])
async function setAutomation(key: 'chores' | 'laundry', value: string) {
  const next = { ...props.equipment.automation } as Record<string, string>
  if (value === '__default') delete next[key]
  else next[key] = value
  await save({ automation: next as EquipmentIn['automation'] })
}
const showLaundry = computed(() => ['washer', 'dryer'].includes(props.equipment.kind) || props.equipment.automation.laundry != null)
</script>

<template>
  <v-card variant="flat" border>
    <v-card-item prepend-icon="mdi-home-assistant">
      <v-card-title class="text-subtitle-1 font-weight-medium">{{ t.appliances.homeAssistant }}</v-card-title>
      <template v-if="isLinked(equipment)" #append>
        <v-menu location="bottom end">
          <template #activator="{ props: menuProps }"><v-btn v-bind="menuProps" icon="mdi-dots-vertical" variant="text" size="small" /></template>
          <v-list density="compact">
            <v-list-item prepend-icon="mdi-link-variant" :title="t.appliances.linkDevice" @click="openPicker('device')" />
            <v-list-item prepend-icon="mdi-plus" :title="t.appliances.addEntity" @click="openPicker('entity')" />
            <v-divider />
            <v-list-item prepend-icon="mdi-link-variant-off" base-color="error" :title="t.appliances.unlink" @click="confirmUnlink = true" />
          </v-list>
        </v-menu>
      </template>
    </v-card-item>
    <v-card-text class="pt-0">
      <template v-if="!isLinked(equipment)">
        <div class="text-body-2 text-medium-emphasis mb-3">{{ t.appliances.notLinked }}</div>
        <div class="d-flex flex-wrap ga-2 mb-4">
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-link-variant" @click="openPicker('device')">{{ t.appliances.linkDevice }}</v-btn>
          <v-btn variant="tonal" prepend-icon="mdi-plus" @click="openPicker('entity')">{{ t.appliances.addEntity }}</v-btn>
        </div>
      </template>
      <template v-else>
        <div v-if="equipment.ha_device_id" class="d-flex align-center mb-2">
          <v-icon icon="mdi-devices" size="18" class="mr-2 text-medium-emphasis" />
          <div class="min-w-0">
            <div class="text-caption text-medium-emphasis">{{ t.appliances.device }}</div>
            <div class="text-body-2 font-weight-medium text-truncate">
              {{ device?.name ?? equipment.ha_device_id }}
              <span v-if="device && (device.manufacturer || device.model)" class="text-medium-emphasis font-weight-regular">· {{ [device.manufacturer, device.model].filter(Boolean).join(' ') }}</span>
            </div>
          </div>
        </div>
        <div v-if="equipment.ha_entities.length" class="mb-2">
          <div class="text-caption text-medium-emphasis mb-1">{{ t.appliances.entities }}</div>
          <div class="d-flex flex-wrap ga-1">
            <v-chip v-for="id in equipment.ha_entities" :key="id" size="small" variant="outlined" label closable :disabled="busy" @click:close="removeEntity(id)">{{ id }}</v-chip>
          </div>
        </div>
      </template>

      <v-select
        :model-value="equipment.kind"
        :items="kindItems"
        :label="t.appliances.kind"
        :disabled="busy"
        :prepend-inner-icon="kindIcon[equipment.kind] ?? 'mdi-devices'"
        class="mt-2"
        hide-details
        @update:model-value="(v: string) => save({ kind: v })"
      />
      <v-select
        :model-value="equipment.automation.chores ?? '__default'"
        :items="choreItems"
        :label="t.appliances.whenFinished"
        :hint="t.appliances.choresHint"
        persistent-hint
        :disabled="busy"
        prepend-inner-icon="mdi-broom"
        class="mt-4"
        @update:model-value="(v: string) => setAutomation('chores', v)"
      />
      <v-select
        v-if="showLaundry"
        :model-value="equipment.automation.laundry ?? '__default'"
        :items="laundryItems"
        :label="t.appliances.laundry"
        :disabled="busy"
        prepend-inner-icon="mdi-tshirt-crew-outline"
        class="mt-2"
        hide-details
        @update:model-value="(v: string) => setAutomation('laundry', v)"
      />
    </v-card-text>

    <HaPickerDialog v-model="pickerOpen" :mode="pickerMode" :equipment="equipment" :busy="busy" @device="linkDevice" @entity="addEntity" />
    <ConfirmDialog v-model="confirmUnlink" :title="t.appliances.unlink" :text="t.appliances.confirmUnlink(equipment.name)" :confirm-label="t.appliances.unlink" @confirm="unlink" />
  </v-card>
</template>
