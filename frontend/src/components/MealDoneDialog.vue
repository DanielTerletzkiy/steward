<script setup lang="ts">
import { ref } from 'vue'
import { t } from '@/i18n'
import { completeMeal } from '@/composables/recipes'
import type { MealPlanEntry } from '@/types'

// Asks whether the ingredients should leave stock when a planned recipe is marked as eaten.
const open = defineModel<boolean>({ default: false })
const props = defineProps<{ entry: MealPlanEntry | null; name: string }>()
const emit = defineEmits<{ done: [] }>()
const busy = ref<'cook' | 'only' | null>(null)

async function finish(cook: boolean) {
  if (!props.entry) return
  busy.value = cook ? 'cook' : 'only'
  const ok = await completeMeal(props.entry, cook)
  busy.value = null
  if (ok) {
    emit('done')
    open.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" max-width="440">
    <v-card :title="t.mealplan.doneTitle" prepend-icon="mdi-silverware-clean">
      <v-card-text>{{ t.mealplan.doneQuestion(name) }}</v-card-text>
      <v-card-actions class="flex-wrap ga-2 px-4 pb-4">
        <v-btn @click="open = false">{{ t.common.cancel }}</v-btn>
        <v-spacer />
        <v-btn variant="tonal" :loading="busy === 'only'" :disabled="!!busy" @click="finish(false)">{{ t.mealplan.doneOnly }}</v-btn>
        <v-btn color="primary" variant="flat" :loading="busy === 'cook'" :disabled="!!busy" @click="finish(true)">{{ t.mealplan.doneCook }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
