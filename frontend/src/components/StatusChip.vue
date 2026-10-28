<script setup lang="ts">
import { computed } from 'vue'
import { t } from '@/i18n'

const props = defineProps<{ status: string; label?: string; kind?: 'stock' | 'chore' }>()

const map: Record<string, { color: string; icon: string; label: string }> = {
  ok: { color: 'success', icon: 'mdi-check-circle-outline', label: t.status.ok },
  due_soon: { color: 'warning', icon: 'mdi-clock-alert-outline', label: t.status.due_soon },
  expired: { color: 'error', icon: 'mdi-alert-circle-outline', label: t.status.expired },
  out: { color: 'grey', icon: 'mdi-package-variant', label: t.status.out },
  below_min: { color: 'warning', icon: 'mdi-arrow-down-bold-circle-outline', label: t.status.below_min },
  overdue: { color: 'error', icon: 'mdi-alert-circle-outline', label: t.status.overdue },
  due_today: { color: 'warning', icon: 'mdi-calendar-today', label: t.status.due_today },
  chore_due_soon: { color: 'info', icon: 'mdi-calendar-clock', label: t.status.chore_due_soon },
  scheduled: { color: 'success', icon: 'mdi-calendar-check', label: t.status.scheduled },
  manual: { color: 'grey', icon: 'mdi-gesture-tap', label: t.status.manual },
}

const info = computed(() => {
  const key = props.kind === 'chore' && props.status === 'due_soon' ? 'chore_due_soon' : props.status
  return map[key] ?? { color: 'grey', icon: 'mdi-help-circle-outline', label: props.status }
})
</script>

<template>
  <v-chip :color="info.color" :prepend-icon="info.icon" variant="tonal" label class="font-weight-medium">
    {{ label ?? info.label }}
  </v-chip>
</template>
