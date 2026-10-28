<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import { api, fileUrl } from '@/api'
import { LOCALE, t } from '@/i18n'
import { useResource } from '@/composables/resource'
import { useManualSearch, warrantyChip } from '@/composables/equipment'
import { kindIcon, liveSummary } from '@/composables/appliances'
import EmptyState from '@/components/EmptyState.vue'
import EquipmentDialog from '@/components/EquipmentDialog.vue'
import ManualHits from '@/components/ManualHits.vue'
import type { Equipment } from '@/types'

const { smAndUp } = useDisplay()
const router = useRouter()
const { data: items, loading, error, reload } = useResource<Equipment[]>(() => api.equipmentList(), ['equipment'], [])
const search = useManualSearch()
const searchQuery = search.query
const searchActive = computed(() => (searchQuery.value ?? '').trim().length >= 2)

const rooms = computed(() => [...new Set(items.value.map((e) => e.room).filter((r): r is string => !!r))].sort((a, b) => a.localeCompare(b, LOCALE)))
const room = ref<string>('')
const visible = computed(() => (room.value ? items.value.filter((e) => e.room === room.value) : items.value))

const dialog = ref(false)
function created(e: Equipment) {
  router.push(`/equipment/${e.id}`)
}
</script>

<template>
  <div class="page">
    <div class="d-flex align-center mb-4">
      <div>
        <div class="page-title">{{ t.equipment.title }}</div>
        <div class="text-body-2 text-medium-emphasis">{{ t.equipment.count(items.length) }}</div>
      </div>
      <v-spacer />
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="dialog = true">{{ smAndUp ? t.equipment.newItem : t.common.create }}</v-btn>
    </div>

    <v-text-field
      v-model="searchQuery"
      :placeholder="t.equipment.askPlaceholder"
      prepend-inner-icon="mdi-text-box-search-outline"
      :loading="search.searching.value"
      clearable
      hide-details
      variant="solo-filled"
      flat
      rounded="pill"
      class="mb-3"
      style="max-width: 720px"
      @keydown.enter="search.now()"
    />

    <v-expand-transition>
      <v-card v-if="searchActive && (search.searched.value || search.hits.value.length)" variant="flat" border class="mb-5" style="max-width: 720px">
        <v-card-item prepend-icon="mdi-book-search-outline" class="pb-0">
          <v-card-title class="text-subtitle-1 font-weight-medium">{{ t.equipment.hits(search.hits.value.length) }}</v-card-title>
          <template #append><v-btn icon="mdi-close" size="small" variant="text" :title="t.common.close" @click="searchQuery = ''" /></template>
        </v-card-item>
        <v-alert v-if="search.error.value" type="error" variant="tonal" density="compact" class="ma-3" :text="search.error.value" />
        <EmptyState v-else-if="!search.hits.value.length" compact icon="mdi-book-off-outline" :title="t.equipment.noHits" />
        <ManualHits v-else :hits="search.hits.value" />
      </v-card>
    </v-expand-transition>

    <v-chip-group v-if="rooms.length > 1" v-model="room" mandatory selected-class="text-primary" class="mb-2">
      <v-chip value="" variant="outlined" size="default" filter>{{ t.common.all }}<span class="ml-1 text-medium-emphasis">{{ items.length }}</span></v-chip>
      <v-chip v-for="r in rooms" :key="r" :value="r" variant="outlined" size="default" filter>
        {{ r }}<span class="ml-1 text-medium-emphasis">{{ items.filter((e) => e.room === r).length }}</span>
      </v-chip>
    </v-chip-group>

    <v-alert v-if="error" type="error" variant="tonal" :text="error" class="mb-4">
      <template #append><v-btn variant="text" @click="reload">{{ t.app.retry }}</v-btn></template>
    </v-alert>

    <v-row v-if="loading && !items.length" dense>
      <v-col v-for="i in 6" :key="i" cols="12" sm="6" lg="4"><v-skeleton-loader type="list-item-avatar-three-line" class="rounded-xl" /></v-col>
    </v-row>

    <EmptyState v-else-if="!items.length" icon="mdi-washing-machine" :title="t.equipment.empty" :text="t.equipment.emptyHint">
      <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="dialog = true">{{ t.equipment.newItem }}</v-btn>
    </EmptyState>

    <v-row v-else dense>
      <v-col v-for="e in visible" :key="e.id" cols="12" sm="6" lg="4">
        <v-card variant="flat" border class="h-100" :to="`/equipment/${e.id}`">
          <div class="d-flex align-stretch pa-3 ga-3">
            <v-sheet color="surface-container" rounded="lg" width="88" height="88" class="flex-shrink-0 overflow-hidden d-flex align-center justify-center">
              <v-img v-if="e.photo_id" :src="fileUrl(e.photo_id, true)" cover width="88" height="88" />
              <v-icon v-else :icon="kindIcon[e.kind] ?? 'mdi-washing-machine'" size="36" class="opacity-50" />
            </v-sheet>
            <div class="min-w-0 flex-grow-1 d-flex flex-column">
              <div class="text-subtitle-1 font-weight-medium text-truncate">{{ e.name }}</div>
              <div class="text-body-2 text-medium-emphasis text-truncate">{{ [e.brand, e.model].filter(Boolean).join(' · ') || ' ' }}</div>
              <v-spacer />
              <div class="d-flex flex-wrap ga-1 mt-2">
                <template v-for="l in e.live ? [liveSummary(e.kind, e.live)] : []" :key="'live'">
                  <v-chip :color="l.color" :variant="l.running || l.color ? 'flat' : 'tonal'" label :class="{ 'opacity-60': l.off }">
                    <template #prepend><span class="live-dot mr-2" :class="{ 'live-dot--on': l.running }" /></template>
                    {{ l.text }}
                  </v-chip>
                </template>
                <v-chip v-if="e.room" variant="outlined" prepend-icon="mdi-floor-plan" label>{{ e.room }}</v-chip>
                <template v-for="w in [warrantyChip(e)]" :key="0">
                  <v-chip v-if="w" :color="w.color" :variant="w.variant" :prepend-icon="w.icon" label :class="w.muted ? 'opacity-60' : ''">{{ w.text }}</v-chip>
                </template>
                <v-chip v-if="e.documents.length" variant="text" prepend-icon="mdi-paperclip" label class="px-1">{{ e.documents.length }}</v-chip>
              </div>
            </div>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <EquipmentDialog v-model="dialog" :rooms="rooms" @saved="created" />
  </div>
</template>

<style scoped>
.live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.6;
  display: inline-block;
}
.live-dot--on {
  opacity: 1;
  animation: blink 1.6s ease-in-out infinite;
}
@keyframes blink {
  50% {
    opacity: 0.35;
  }
}
</style>
