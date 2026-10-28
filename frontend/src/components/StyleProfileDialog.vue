<script setup lang="ts">
import { ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { api } from '@/api'
import { t } from '@/i18n'
import { attempt, notify } from '@/composables/notify'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ owner?: string | null; ownerName?: string | null }>()
const { xs } = useDisplay()

const form = ref({ description: '', likes: [] as string[], dislikes: [] as string[], runs_warm: 0 })
const loading = ref(false)
const busy = ref(false)

watch(open, async (v) => {
  if (!v) return
  loading.value = true
  const p = await attempt(() => api.styleProfile(props.owner))
  loading.value = false
  if (p) form.value = { description: p.description ?? '', likes: [...p.likes], dislikes: [...p.dislikes], runs_warm: p.runs_warm }
})

const clean = (list: string[]) => [...new Set(list.map((s) => s.trim()).filter(Boolean))]

async function save() {
  busy.value = true
  const f = form.value
  const res = await attempt(() =>
    api.setStyleProfile({ description: f.description.trim() || null, likes: clean(f.likes), dislikes: clean(f.dislikes), runs_warm: f.runs_warm }, props.owner),
  )
  busy.value = false
  if (res) {
    notify(t.wardrobe.profileSaved)
    open.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" :fullscreen="xs" max-width="560" scrollable>
    <v-card :rounded="xs ? 0 : 'xl'">
      <v-toolbar color="transparent" density="comfortable">
        <v-btn icon="mdi-close" :title="t.common.close" @click="open = false" />
        <v-toolbar-title class="font-weight-medium">{{ ownerName ? t.wardrobe.profileFor(ownerName) : t.wardrobe.profile }}</v-toolbar-title>
      </v-toolbar>
      <v-progress-linear v-if="loading" indeterminate color="primary" />
      <v-card-text>
        <div class="text-body-2 text-medium-emphasis mb-4">{{ t.wardrobe.profileHint }}</div>
        <v-textarea v-model="form.description" :label="t.wardrobe.description" :placeholder="t.wardrobe.descriptionPlaceholder" rows="3" auto-grow persistent-placeholder />
        <v-combobox
          v-model="form.likes"
          :label="t.wardrobe.likes"
          prepend-inner-icon="mdi-thumb-up-outline"
          multiple
          chips
          closable-chips
          :hint="t.wardrobe.chipsHint"
          class="mb-2"
        />
        <v-combobox
          v-model="form.dislikes"
          :label="t.wardrobe.dislikes"
          prepend-inner-icon="mdi-thumb-down-outline"
          multiple
          chips
          closable-chips
          :hint="t.wardrobe.chipsHint"
          class="mb-2"
        />
        <div class="d-flex justify-space-between text-caption text-medium-emphasis mt-2">
          <span>{{ t.wardrobe.runsWarm }}</span>
          <span class="text-primary font-weight-medium">{{ t.wardrobe.runsWarmLabels[form.runs_warm + 2] }}</span>
        </div>
        <v-slider v-model="form.runs_warm" :min="-2" :max="2" :step="1" show-ticks="always" tick-size="4" color="primary" hide-details prepend-icon="mdi-snowflake" append-icon="mdi-white-balance-sunny" />
        <div class="d-flex justify-space-between text-caption text-medium-emphasis px-10">
          <span>{{ t.wardrobe.runsWarmLabels[0] }}</span><span>{{ t.wardrobe.runsWarmLabels[4] }}</span>
        </div>
      </v-card-text>
      <v-divider />
      <v-card-actions class="px-4">
        <v-spacer />
        <v-btn @click="open = false">{{ t.common.cancel }}</v-btn>
        <v-btn color="primary" variant="flat" :loading="busy" :disabled="loading" @click="save">{{ t.common.save }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
