<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { attempt } from '@/composables/notify'
import { daysFromToday, formatDateTime, formatTime, parseDateTime } from '@/composables/format'
import { laundryDone } from '@/composables/wardrobe'
import type { Garment, LaundryPrompt } from '@/types'

// "The washing machine finished: mark the laundry clean?" Shown on Today and in the wardrobe.
const props = defineProps<{ prompt: LaundryPrompt; pieces?: Pick<Garment, 'id' | 'state' | 'wears_since_wash'>[] }>()
const emit = defineEmits<{ changed: [] }>()

const when = computed(() => (daysFromToday(parseDateTime(props.prompt.at)) === 0 ? formatTime(props.prompt.at) : formatDateTime(props.prompt.at)))
const busy = ref<'clean' | 'dismiss' | null>(null)

async function markClean() {
  busy.value = 'clean'
  // Explicit ids give an exact undo; the server clears the prompt either way.
  const ok = await laundryDone(props.pieces ?? [])
  busy.value = null
  if (ok) emit('changed')
}
async function dismiss() {
  busy.value = 'dismiss'
  const ok = await attempt(async () => (await api.dismissLaundryPrompt(), true))
  busy.value = null
  if (ok) emit('changed')
}
</script>

<template>
  <v-card color="secondary" variant="tonal">
    <div class="d-flex flex-column flex-sm-row align-sm-center ga-3 pa-4">
      <div class="d-flex align-center flex-grow-1 min-w-0">
        <v-avatar color="secondary" variant="flat" class="mr-3 flex-shrink-0"><v-icon icon="mdi-washing-machine" /></v-avatar>
        <div class="text-body-1 text-high-emphasis">{{ t.appliances.laundryPrompt(prompt.name, when, prompt.pieces) }}</div>
      </div>
      <div class="d-flex ga-2 flex-shrink-0 justify-end">
        <v-btn variant="text" :loading="busy === 'dismiss'" :disabled="!!busy" @click="dismiss">{{ t.appliances.notNow }}</v-btn>
        <v-btn color="primary" variant="flat" prepend-icon="mdi-check-all" :loading="busy === 'clean'" :disabled="!!busy" @click="markClean">{{ t.appliances.markClean }}</v-btn>
      </div>
    </div>
  </v-card>
</template>
