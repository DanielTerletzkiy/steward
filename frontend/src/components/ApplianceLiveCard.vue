<script setup lang="ts">
import { computed, ref } from 'vue'
import { api, ApiError } from '@/api'
import { t } from '@/i18n'
import { notify, notifyError } from '@/composables/notify'
import { relativeTime } from '@/composables/format'
import { batteryIcon, commandIcon, commandLabel, kindIcon, stateLabel } from '@/composables/appliances'
import type { Equipment } from '@/types'

// What a linked appliance is doing right now, pushed by Home Assistant, with its commands.
const props = defineProps<{ equipment: Equipment }>()
const live = computed(() => props.equipment.live!)
const isError = computed(() => (live.value.state ?? '').toLowerCase() === 'error')
const details = ref(false)

const sending = ref<string | null>(null)
async function send(command: string) {
  sending.value = command
  try {
    await api.equipmentCommand(props.equipment.id, command)
    notify(t.appliances.commandSent(commandLabel(command)))
  } catch (e) {
    notifyError(e instanceof ApiError && e.status === 503 ? new Error(t.appliances.haOffline) : e)
  } finally {
    sending.value = null
  }
}
</script>

<template>
  <v-card :variant="live.running ? 'tonal' : 'flat'" :color="isError ? 'error' : live.running ? 'primary' : undefined" :border="!live.running && !isError">
    <v-card-item>
      <template #prepend>
        <v-avatar :color="isError ? 'error' : 'primary'" :variant="live.running ? 'flat' : 'tonal'" size="48" :class="{ pulse: live.running }">
          <v-icon :icon="kindIcon[equipment.kind] ?? 'mdi-devices'" size="26" />
        </v-avatar>
      </template>
      <div class="text-overline" style="line-height: 1.4">{{ t.appliances.live }}</div>
      <v-card-title class="text-h6 font-weight-bold" style="line-height: 1.25">{{ stateLabel(live.state) }}</v-card-title>
      <v-card-subtitle class="opacity-90 d-flex flex-wrap align-center ga-2 mt-1">
        <span v-if="live.running && live.remaining_minutes != null" class="font-weight-medium">
          <v-icon icon="mdi-timer-sand" size="14" class="mr-1" />{{ t.appliances.minutesLeft(live.remaining_minutes) }}
        </span>
        <span v-else>{{ live.running ? t.appliances.running : t.appliances.notRunning }}</span>
        <span v-if="live.battery != null"><v-icon :icon="batteryIcon(live.battery)" size="16" class="mr-1" />{{ t.appliances.battery(live.battery) }}</span>
      </v-card-subtitle>
    </v-card-item>
    <v-progress-linear v-if="live.running" indeterminate color="primary" height="3" class="mx-4" style="width: auto" rounded />
    <v-card-actions v-if="live.commands.length" class="px-4 pt-3 flex-wrap ga-2">
      <v-btn
        v-for="c in live.commands"
        :key="c"
        :variant="c === 'start' && !live.running ? 'flat' : 'tonal'"
        :color="c === 'start' && !live.running ? 'primary' : undefined"
        size="small"
        :prepend-icon="commandIcon[c] ?? 'mdi-gesture-tap'"
        :loading="sending === c"
        :disabled="!!sending && sending !== c"
        @click="send(c)"
      >{{ commandLabel(c) }}</v-btn>
    </v-card-actions>
    <div class="d-flex align-center px-4 pb-2" :class="live.commands.length ? '' : 'pt-2'">
      <span v-if="equipment.live_at" class="text-caption text-medium-emphasis">{{ t.appliances.updated(relativeTime(equipment.live_at)) }}</span>
      <v-spacer />
      <v-btn v-if="live.entities.length" variant="text" size="small" :append-icon="details ? 'mdi-chevron-up' : 'mdi-chevron-down'" @click="details = !details">{{ t.appliances.details }}</v-btn>
    </div>
    <v-expand-transition>
      <div v-if="details">
        <v-divider />
        <v-list density="compact" bg-color="transparent">
          <v-list-item v-for="e in live.entities" :key="e.entity_id" :title="e.name || e.entity_id" :subtitle="e.name ? e.entity_id : undefined">
            <template #append>
              <span class="text-body-2 text-tabular">{{ e.state == null ? '–' : `${stateLabel(e.state)}${e.unit ? ` ${e.unit}` : ''}` }}</span>
            </template>
          </v-list-item>
        </v-list>
      </div>
    </v-expand-transition>
  </v-card>
</template>

<style scoped>
.pulse {
  animation: pulse 2s ease-in-out infinite;
}
@keyframes pulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(var(--v-theme-primary), 0.45);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(var(--v-theme-primary), 0);
  }
}
</style>
