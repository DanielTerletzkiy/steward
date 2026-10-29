<script setup lang="ts">
import { ref } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { useCatalog } from '@/composables/catalog'
import { attempt, notify } from '@/composables/notify'
import ConfirmDialog from './ConfirmDialog.vue'
import type { Location } from '@/types'

// Settings: add, rename, mark as freezer and remove storage locations.
const { state, refresh } = useCatalog()

const newName = ref('')
const adding = ref(false)
async function add(name = newName.value) {
  const value = name.trim()
  if (!value) return
  adding.value = true
  const created = await attempt(() => api.createLocation(value, /gefrier|freez|tiefk/i.test(value)))
  adding.value = false
  if (!created) return
  newName.value = ''
  await refresh()
  notify(t.locations.added(created.name))
}

const editingId = ref<number | null>(null)
const editName = ref('')
function startRename(l: Location) {
  editingId.value = l.id
  editName.value = l.name
}
async function rename(l: Location) {
  const value = editName.value.trim()
  editingId.value = null
  if (!value || value === l.name) return
  if (await attempt(() => api.updateLocation(l.id, { name: value }))) await refresh()
}

async function setFreezer(l: Location, value: boolean | null) {
  if (await attempt(() => api.updateLocation(l.id, { is_freezer: !!value }))) await refresh()
}

const removing = ref<Location | null>(null)
const confirmOpen = ref(false)
function askRemove(l: Location) {
  removing.value = l
  confirmOpen.value = true
}
async function remove() {
  const l = removing.value
  if (!l) return
  if (await attempt(async () => (await api.deleteLocation(l.id), true))) {
    await refresh()
    notify(t.locations.deleted)
  }
}

const suggestions = () => t.locations.suggestions.filter((x) => !state.locations.some((l) => l.name.toLowerCase() === x.toLowerCase()))
</script>

<template>
  <v-card variant="flat" border class="mb-6">
    <v-list v-if="state.locations.length" bg-color="transparent" class="py-0">
      <template v-for="(l, i) in state.locations" :key="l.id">
        <v-divider v-if="i > 0" />
        <v-list-item class="py-2">
          <template #prepend>
            <v-icon :icon="l.is_freezer ? 'mdi-snowflake' : 'mdi-map-marker-outline'" :color="l.is_freezer ? 'info' : undefined" />
          </template>
          <v-text-field
            v-if="editingId === l.id"
            v-model="editName"
            density="compact"
            hide-details
            autofocus
            @keydown.enter="rename(l)"
            @keydown.esc="editingId = null"
            @blur="rename(l)"
          />
          <v-list-item-title v-else class="clickable" @click="startRename(l)">{{ l.name }}</v-list-item-title>
          <template #append>
            <v-switch
              :model-value="l.is_freezer"
              :label="t.locations.freezer"
              color="info"
              density="compact"
              hide-details
              inset
              class="mr-2"
              @update:model-value="setFreezer(l, $event)"
            />
            <v-btn icon="mdi-pencil-outline" variant="text" size="small" :title="t.locations.rename" @click="startRename(l)" />
            <v-btn icon="mdi-delete-outline" variant="text" size="small" :title="t.common.delete" @click="askRemove(l)" />
          </template>
        </v-list-item>
      </template>
      <v-divider />
    </v-list>
    <v-card-text>
      <div v-if="!state.locations.length" class="mb-3">
        <div class="text-subtitle-2">{{ t.locations.empty }}</div>
        <div class="text-body-2 text-medium-emphasis">{{ t.locations.emptyHint }}</div>
      </div>
      <div class="d-flex ga-2 align-center">
        <v-text-field v-model="newName" :label="t.locations.add" density="compact" hide-details @keydown.enter="add()" />
        <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" :loading="adding" :disabled="!newName.trim()" @click="add()">{{ t.common.add }}</v-btn>
      </div>
      <div v-if="suggestions().length" class="d-flex flex-wrap ga-1 mt-3">
        <v-chip v-for="s in suggestions()" :key="s" size="small" variant="tonal" prepend-icon="mdi-plus" @click="add(s)">{{ s }}</v-chip>
      </div>
    </v-card-text>
  </v-card>
  <ConfirmDialog v-model="confirmOpen" :title="t.common.delete" :text="removing ? t.locations.confirmDelete(removing.name) : ''" @confirm="remove" />
</template>
