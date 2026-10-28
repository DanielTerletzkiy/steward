<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { notify } from '@/composables/notify'
import type { Recipe } from '@/types'

const open = defineModel<boolean>({ default: false })
const emit = defineEmits<{ imported: [Recipe] }>()
const url = ref('')
const busy = ref(false)
const error = ref<string | null>(null)
watch(open, (v) => {
  if (v) {
    url.value = ''
    error.value = null
  }
})

async function run() {
  const u = url.value.trim()
  if (!u) return
  busy.value = true
  error.value = null
  try {
    const r = await api.importRecipe(u)
    notify(t.recipes.imported)
    emit('imported', r)
    open.value = false
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" max-width="520">
    <v-card :title="t.recipes.importTitle" prepend-icon="mdi-web">
      <v-card-text>
        <v-form @submit.prevent="run">
          <v-text-field v-model="url" :label="t.recipes.importUrl" placeholder="https://…" inputmode="url" autofocus :hint="t.recipes.importHint" persistent-hint :disabled="busy" />
        </v-form>
        <v-progress-linear v-if="busy" indeterminate color="primary" rounded class="mt-3" />
        <v-alert v-if="error" type="error" variant="tonal" density="compact" :text="error" class="mt-3" />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="open = false">{{ t.common.cancel }}</v-btn>
        <v-btn color="primary" variant="flat" :loading="busy" :disabled="!url.trim()" @click="run">{{ t.recipes.import }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
