<script setup lang="ts">
import { ref } from 'vue'
import { useDisplay } from 'vuetify'
import { api } from '@/api'
import { t } from '@/i18n'
import { useCatalog } from '@/composables/catalog'
import { attempt, notify } from '@/composables/notify'
import { formatDate, formatEuro, formatTime, parseDateTime, parseDay, relativeDay, daysFromToday } from '@/composables/format'
import { label, markDry, setGarmentState, stateColor, stateIcon, stillFine, swatch, toLaundry, useVocabulary, wearToday } from '@/composables/wardrobe'
import GarmentThumb from './GarmentThumb.vue'
import ConfirmDialog from './ConfirmDialog.vue'
import type { Garment, GarmentState } from '@/types'

const open = defineModel<boolean>({ default: false })
defineProps<{ garment: Garment | null }>()
const emit = defineEmits<{ edit: [Garment] }>()
const { xs } = useDisplay()
const { state, personName } = useCatalog()
const vocab = useVocabulary()
const confirmDelete = ref(false)

function dryText(g: Garment) {
  if (!g.dry_until) return t.wardrobe.dryManual
  return t.wardrobe.dryUntil(`${relativeDay(daysFromToday(parseDateTime(g.dry_until)))} ${formatTime(g.dry_until)}`)
}

function lastWorn(g: Garment) {
  if (!g.last_worn) return t.wardrobe.neverWorn
  const n = daysFromToday(parseDay(g.last_worn))
  return n >= -6 ? relativeDay(n) : formatDate(g.last_worn)
}

async function toggleFavorite(g: Garment) {
  await attempt(() => api.updateGarment(g.id, { favorite: !g.favorite }))
}
async function remove(g: Garment) {
  const ok = await attempt(async () => (await api.deleteGarment(g.id), true))
  if (ok) {
    notify(t.wardrobe.pieceDeleted)
    open.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" :fullscreen="xs" max-width="640" scrollable>
    <v-card v-if="garment" :rounded="xs ? 0 : 'xl'">
      <v-toolbar color="transparent" density="comfortable">
        <v-btn icon="mdi-close" :title="t.common.close" @click="open = false" />
        <v-spacer />
        <v-btn
          :icon="garment.favorite ? 'mdi-heart' : 'mdi-heart-outline'"
          :color="garment.favorite ? 'error' : undefined"
          :title="t.wardrobe.favorite"
          @click="toggleFavorite(garment)"
        />
        <v-btn icon="mdi-pencil-outline" :title="t.common.edit" @click="emit('edit', garment)" />
        <v-btn icon="mdi-delete-outline" :title="t.wardrobe.deletePiece" @click="confirmDelete = true" />
      </v-toolbar>
      <v-card-text class="pt-0">
        <v-row>
          <v-col cols="12" sm="6">
            <GarmentThumb :photo-id="garment.photo_id" :layer="garment.layer" full rounded="xl" :icon-size="72" />
          </v-col>
          <v-col cols="12" sm="6">
            <div class="text-h6 font-weight-medium" style="line-height: 1.3">{{ garment.name }}</div>
            <div class="text-body-2 text-medium-emphasis">
              {{ label.category(garment.category) }} · {{ label.layer(garment.layer) }}
              <template v-if="garment.brand"> · {{ garment.brand }}</template>
              <template v-if="garment.size"> · {{ garment.size }}</template>
            </div>
            <div v-if="state.people.length > 1" class="text-caption text-medium-emphasis mt-1">
              <v-icon icon="mdi-account-outline" size="14" /> {{ personName(garment.owner) ?? t.wardrobe.household }}
            </div>
            <div v-if="garment.colors.length" class="d-flex flex-wrap ga-1 mt-3">
              <v-chip v-for="c in garment.colors" :key="c" variant="outlined">
                <template #prepend><span class="swatch mr-1" :style="{ background: swatch(c) }" /></template>
                {{ label.color(c) }}
              </v-chip>
              <v-chip v-if="garment.pattern" variant="outlined">{{ label.pattern(garment.pattern) }}</v-chip>
              <v-chip v-if="garment.material" variant="outlined">{{ garment.material }}</v-chip>
            </div>
            <div class="d-flex flex-wrap ga-1 mt-2">
              <v-chip variant="tonal" prepend-icon="mdi-fire">{{ t.wardrobe.warmthLabels[garment.warmth - 1] }}</v-chip>
              <v-chip v-if="garment.temp_min != null || garment.temp_max != null" variant="tonal" prepend-icon="mdi-thermometer">
                {{ garment.temp_min ?? '…' }} – {{ garment.temp_max ?? '…' }} °C
              </v-chip>
              <v-chip v-if="garment.rain !== 'none'" variant="tonal" prepend-icon="mdi-weather-pouring">{{ label.rain(garment.rain) }}</v-chip>
              <v-chip v-if="garment.windproof" variant="tonal" prepend-icon="mdi-weather-windy">{{ t.wardrobe.windproof }}</v-chip>
              <v-chip variant="tonal" prepend-icon="mdi-tie">{{ t.wardrobe.formalityLabels[garment.formality - 1] }}</v-chip>
              <v-chip v-for="u in garment.uses" :key="u" variant="tonal" color="primary">{{ label.use(u) }}</v-chip>
              <v-chip v-for="s in garment.seasons" :key="s" variant="tonal" color="secondary">{{ label.season(s) }}</v-chip>
            </div>
          </v-col>
        </v-row>

        <v-row dense class="mt-2">
          <v-col cols="6" sm="3">
            <v-sheet color="surface-container" rounded="lg" class="pa-3 h-100">
              <div class="text-caption text-medium-emphasis">{{ t.wardrobe.wearCount }}</div>
              <div class="text-subtitle-1 font-weight-bold text-tabular">{{ t.wardrobe.wearCountValue(garment.wear_count) }}</div>
            </v-sheet>
          </v-col>
          <v-col cols="6" sm="3">
            <v-sheet color="surface-container" rounded="lg" class="pa-3 h-100">
              <div class="text-caption text-medium-emphasis">{{ t.wardrobe.lastWorn }}</div>
              <div class="text-subtitle-1 font-weight-bold">{{ lastWorn(garment) }}</div>
            </v-sheet>
          </v-col>
          <v-col cols="6" sm="3">
            <v-sheet color="surface-container" rounded="lg" class="pa-3 h-100">
              <div class="text-caption text-medium-emphasis">{{ t.wardrobe.costPerWear }}</div>
              <div class="text-subtitle-1 font-weight-bold text-tabular">{{ formatEuro(garment.cost_per_wear) }}</div>
            </v-sheet>
          </v-col>
          <v-col cols="6" sm="3">
            <v-sheet color="surface-container" rounded="lg" class="pa-3 h-100">
              <div class="text-caption text-medium-emphasis">{{ t.wardrobe.sinceWash }}</div>
              <div class="text-subtitle-1 font-weight-bold text-tabular">{{ t.wardrobe.sinceWashValue(garment.wears_since_wash, garment.wears_per_wash) }}</div>
            </v-sheet>
          </v-col>
        </v-row>

        <v-alert
          v-if="garment.needs_wash && (garment.state === 'clean' || garment.state === 'worn')"
          type="warning"
          variant="tonal"
          density="compact"
          icon="mdi-basket-plus-outline"
          class="mt-4"
          :title="t.wardrobe.readyForWash"
        >
          <div class="d-flex flex-wrap ga-2 mt-2">
            <v-btn size="small" variant="flat" color="warning" prepend-icon="mdi-basket-plus-outline" @click="toLaundry([garment])">{{ t.wardrobe.toLaundry }}</v-btn>
            <v-btn size="small" variant="text" @click="stillFine([garment])">{{ t.wardrobe.stillFine }}</v-btn>
          </div>
        </v-alert>
        <v-alert v-else-if="garment.state === 'drying'" type="info" variant="tonal" density="compact" icon="mdi-weather-windy" class="mt-4">
          <div class="d-flex flex-wrap align-center ga-2">
            <span>{{ label.state('drying') }} · {{ dryText(garment) }}</span>
            <v-spacer />
            <v-btn size="small" variant="flat" color="info" prepend-icon="mdi-weather-sunny" @click="markDry([garment])">{{ t.wardrobe.dryNow }}</v-btn>
          </div>
        </v-alert>
        <div class="text-caption text-medium-emphasis mt-4 mb-1">{{ t.wardrobe.state }}</div>
        <v-chip-group :model-value="garment.state" mandatory column @update:model-value="(s: GarmentState) => setGarmentState(garment!, s)">
          <v-chip
            v-for="s in vocab?.states ?? []"
            :key="s"
            :value="s"
            :color="s === garment.state ? stateColor[s] : undefined"
            :variant="s === garment.state ? 'tonal' : 'outlined'"
            :prepend-icon="stateIcon[s]"
            size="default"
          >
            {{ label.state(s) }}
          </v-chip>
        </v-chip-group>

        <div v-if="garment.notes" class="text-body-2 mt-3" style="white-space: pre-line">{{ garment.notes }}</div>
        <div v-if="garment.price != null" class="text-caption text-medium-emphasis mt-2">{{ t.common.price }}: {{ formatEuro(garment.price) }}</div>
      </v-card-text>
      <v-divider />
      <v-card-actions class="px-4">
        <v-btn variant="text" prepend-icon="mdi-pencil-outline" @click="emit('edit', garment)">{{ t.common.edit }}</v-btn>
        <v-spacer />
        <v-btn color="primary" variant="flat" prepend-icon="mdi-tshirt-crew" @click="wearToday([garment.id])">{{ t.wardrobe.wearToday }}</v-btn>
      </v-card-actions>
      <ConfirmDialog v-model="confirmDelete" :title="t.wardrobe.deletePiece" :text="t.wardrobe.confirmDelete(garment.name)" @confirm="remove(garment)" />
    </v-card>
  </v-dialog>
</template>

