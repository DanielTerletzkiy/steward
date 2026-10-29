<script setup lang="ts">
import { ref } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { useCatalog } from '@/composables/catalog'
import { attempt, notify } from '@/composables/notify'

// A location picker that can also create a new location on the spot.
const model = defineModel<number | null>({ default: null })
withDefaults(defineProps<{ label?: string }>(), { label: undefined })
const { state, refresh } = useCatalog()

const adding = ref(false)
const name = ref('')
const busy = ref(false)

function startAdding() {
  name.value = ''
  adding.value = true
}

async function create() {
  const value = name.value.trim()
  if (!value) return
  busy.value = true
  const created = await attempt(() => api.createLocation(value))
  busy.value = false
  if (!created) return
  await refresh()
  model.value = created.id
  adding.value = false
  notify(t.locations.added(created.name))
}
</script>

<template>
  <v-select v-model="model" :label="label ?? t.common.location" :items="state.locations" item-title="name" item-value="id" clearable>
    <template #item="{ props: itemProps, item }">
      <v-list-item v-bind="itemProps" :prepend-icon="item.raw.is_freezer ? 'mdi-snowflake' : 'mdi-map-marker-outline'" />
    </template>
    <template #append-item>
      <v-divider v-if="state.locations.length" class="my-1" />
      <v-list-item prepend-icon="mdi-plus" :title="t.locations.new" @click="startAdding" />
    </template>
  </v-select>
  <v-dialog v-model="adding" max-width="400">
    <v-card :title="t.locations.add">
      <v-card-text>
        <v-text-field v-model="name" :label="t.locations.name" autofocus @keydown.enter="create" />
        <div class="d-flex flex-wrap ga-1">
          <v-chip
            v-for="s in t.locations.suggestions.filter((x) => !state.locations.some((l) => l.name.toLowerCase() === x.toLowerCase()))"
            :key="s"
            size="small"
            variant="tonal"
            @click="name = s"
          >{{ s }}</v-chip>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="adding = false">{{ t.common.cancel }}</v-btn>
        <v-btn color="primary" variant="flat" :loading="busy" :disabled="!name.trim()" @click="create">{{ t.common.add }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
