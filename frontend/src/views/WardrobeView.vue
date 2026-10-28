<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { api } from '@/api'
import { LOCALE, t } from '@/i18n'
import { useResource } from '@/composables/resource'
import { useCatalog } from '@/composables/catalog'
import { attempt, notify } from '@/composables/notify'
import { daysFromToday, formatShortDate, parseDay, relativeDay } from '@/composables/format'
import { label, laundryDone, layerIcon, sourceIcon, stateColor, stateIcon, useVocabulary, wearToday } from '@/composables/wardrobe'
import EmptyState from '@/components/EmptyState.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import GarmentThumb from '@/components/GarmentThumb.vue'
import GarmentDialog from '@/components/GarmentDialog.vue'
import GarmentSheet from '@/components/GarmentSheet.vue'
import OutfitCollage from '@/components/OutfitCollage.vue'
import StyleProfileDialog from '@/components/StyleProfileDialog.vue'
import TodayOutfitCard from '@/components/TodayOutfitCard.vue'
import LaundryPromptBanner from '@/components/LaundryPromptBanner.vue'
import type { Garment, Outfit, Summary } from '@/types'

const { xs, smAndUp, mdAndUp, lgAndUp } = useDisplay()
const { state: catalog, personName } = useCatalog()
const vocab = useVocabulary()

function load<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(`steward.wardrobe.${key}`)
    return v ? (JSON.parse(v) as T) : fallback
  } catch {
    return fallback
  }
}
function store(key: string, value: unknown) {
  try {
    localStorage.setItem(`steward.wardrobe.${key}`, JSON.stringify(value))
  } catch {
    /* storage unavailable */
  }
}

// '' = everyone (no owner filter).
const owner = ref<string>(load('owner', ''))
const showOwners = computed(() => catalog.people.length > 1)
const ownerParam = computed(() => (showOwners.value && owner.value ? owner.value : null))

const { data: garments, loading, error, reload } = useResource<Garment[]>(() => api.garments(ownerParam.value), ['wardrobe', 'people'], [])
const { data: outfits, reload: reloadOutfits } = useResource<Outfit[]>(() => api.outfits({ owner: ownerParam.value, limit: 40 }), ['wardrobe'], [])
watch(ownerParam, () => {
  store('owner', owner.value)
  reload()
  reloadOutfits()
})

// Only for the "washer finished" laundry prompt.
const { data: summary, reload: reloadSummary } = useResource<Summary | null>(() => api.summary(), ['wardrobe', 'settings', 'equipment'], null)
const laundryPrompt = computed(() => summary.value?.wardrobe.laundry_prompt ?? null)

const byId = computed(() => new Map(garments.value.map((g) => [g.id, g])))

// --- filters
const tab = ref<'closet' | 'outfits'>(load('tab', 'closet'))
const layer = ref<string>(load('layer', 'all'))
const stateFilter = ref<string | null>(null)
const useFilter = ref<string | null>(null)
const seasonFilter = ref<string | null>(null)
const favorites = ref(false)
const search = ref('')
watch([tab, layer], () => {
  store('tab', tab.value)
  store('layer', layer.value)
})
const filtersActive = computed(() => !!(stateFilter.value || useFilter.value || seasonFilter.value || favorites.value || search.value))
function resetFilters() {
  stateFilter.value = useFilter.value = seasonFilter.value = null
  favorites.value = false
  search.value = ''
  layer.value = 'all'
}

const matching = computed(() => {
  const q = search.value.trim().toLowerCase()
  return garments.value.filter((g) => {
    if (stateFilter.value && g.state !== stateFilter.value) return false
    if (useFilter.value && !g.uses.includes(useFilter.value)) return false
    if (seasonFilter.value && !g.seasons.includes(seasonFilter.value)) return false
    if (favorites.value && !g.favorite) return false
    if (q) {
      const text = [g.name, g.brand, g.material, label.category(g.category), ...g.colors.map(label.color)].join(' ').toLowerCase()
      if (!text.includes(q)) return false
    }
    return true
  })
})
const layers = computed(() => vocab.value?.layers ?? [...new Set(garments.value.map((g) => g.layer))])
const layerCounts = computed(() => {
  const counts: Record<string, number> = {}
  for (const g of matching.value) counts[g.layer] = (counts[g.layer] ?? 0) + 1
  return counts
})
const available = (g: Garment) => g.state === 'clean' || g.state === 'worn'
const sortPieces = (list: Garment[]) =>
  [...list].sort((a, b) => Number(available(b)) - Number(available(a)) || Number(b.favorite) - Number(a.favorite) || a.name.localeCompare(b.name, LOCALE))
const groups = computed(() => {
  const visible = layer.value === 'all' ? matching.value : matching.value.filter((g) => g.layer === layer.value)
  if (layer.value !== 'all') return [{ layer: layer.value, items: sortPieces(visible) }]
  const order = layers.value
  return order
    .map((l) => ({ layer: l, items: sortPieces(visible.filter((g) => g.layer === l)) }))
    .concat([{ layer: '', items: sortPieces(visible.filter((g) => !order.includes(g.layer))) }])
    .filter((grp) => grp.items.length)
})
const visibleCount = computed(() => groups.value.reduce((n, g) => n + g.items.length, 0))

const filterMenus = computed(() => [
  { key: 'state', model: stateFilter, any: t.wardrobe.anyState, title: t.wardrobe.state, icon: 'mdi-washing-machine', items: (vocab.value?.states ?? []).map((v) => ({ value: v, title: label.state(v) })) },
  { key: 'use', model: useFilter, any: t.wardrobe.anyUse, title: t.wardrobe.use, icon: 'mdi-briefcase-outline', items: (vocab.value?.uses ?? []).map((v) => ({ value: v, title: label.use(v) })) },
  { key: 'season', model: seasonFilter, any: t.wardrobe.anySeason, title: t.wardrobe.season, icon: 'mdi-weather-partly-snowy', items: (vocab.value?.seasons ?? []).map((v) => ({ value: v, title: label.season(v) })) },
])

// --- laundry
const laundry = computed(() => garments.value.filter((g) => g.state === 'laundry'))
const washing = ref(false)
async function doLaundry() {
  washing.value = true
  await laundryDone(laundry.value)
  washing.value = false
}

// --- selection
const selecting = ref(false)
const selected = ref<number[]>([])
function toggleSelect(g: Garment) {
  const i = selected.value.indexOf(g.id)
  selected.value = i >= 0 ? selected.value.filter((id) => id !== g.id) : [...selected.value, g.id]
}
function stopSelecting() {
  selecting.value = false
  selected.value = []
}
async function wearSelected() {
  if (await wearToday(selected.value)) stopSelecting()
}
const occasionItems = computed(() => (vocab.value?.uses ?? []).map((u) => ({ value: u, title: label.use(u) })))
const outfitDialog = ref(false)
const outfitForm = ref({ occasion: null as string | null, worn: true })
const savingOutfit = ref(false)
function openSaveOutfit() {
  outfitForm.value = { occasion: null, worn: true }
  outfitDialog.value = true
}
async function saveOutfit() {
  savingOutfit.value = true
  const res = await attempt(() =>
    api.createOutfit({ owner: ownerParam.value, garment_ids: selected.value, occasion: outfitForm.value.occasion, worn: outfitForm.value.worn }),
  )
  savingOutfit.value = false
  if (res) {
    notify(outfitForm.value.worn ? t.wardrobe.outfitWorn : t.wardrobe.outfitSaved)
    outfitDialog.value = false
    stopSelecting()
  }
}

function onCard(g: Garment) {
  if (selecting.value) toggleSelect(g)
  else openDetail(g)
}

// --- outfits
function outfitDay(o: Outfit) {
  const n = daysFromToday(parseDay(o.day))
  const rel = n >= -1 && n <= 1 ? relativeDay(n) : formatShortDate(parseDay(o.day))
  return rel.charAt(0).toUpperCase() + rel.slice(1)
}
async function rate(o: Outfit, rating: -1 | 1) {
  await attempt(() => api.outfitFeedback(o.id, o.rating === rating ? 0 : rating, o.feedback))
}
async function wearOutfit(o: Outfit) {
  const res = await attempt(() => api.wearOutfit(o.id))
  if (res) notify(t.wardrobe.outfitWorn)
}
const deleteOutfitFor = ref<Outfit | null>(null)
const confirmOutfit = ref(false)
async function removeOutfit() {
  const o = deleteOutfitFor.value
  if (!o) return
  const ok = await attempt(async () => (await api.deleteOutfit(o.id), true))
  if (ok) notify(t.wardrobe.outfitDeleted)
}

// --- dialogs
const detailId = ref<number | null>(null)
const detailOpen = ref(false)
const detail = computed(() => (detailId.value != null ? byId.value.get(detailId.value) ?? null : null))
watch(detail, (g) => {
  if (!g && detailOpen.value) detailOpen.value = false
})
function openDetail(g: Garment) {
  detailId.value = g.id
  detailOpen.value = true
}
const editFor = ref<Garment | null>(null)
const editOpen = ref(false)
function openEdit(g: Garment | null) {
  editFor.value = g
  editOpen.value = true
}
const profileOpen = ref(false)
</script>

<template>
  <div class="page" :class="{ 'pb-selecting': selecting }">
    <div class="d-flex align-center mb-4">
      <div class="min-w-0">
        <div class="page-title">{{ t.wardrobe.title }}</div>
        <div class="text-body-2 text-medium-emphasis">{{ t.wardrobe.count(garments.length) }}</div>
      </div>
      <v-spacer />
      <v-btn :icon="!smAndUp" variant="text" class="mr-1" :title="t.wardrobe.profile" @click="profileOpen = true">
        <v-icon icon="mdi-account-heart-outline" />
        <span v-if="smAndUp" class="ml-2">{{ t.wardrobe.profile }}</span>
      </v-btn>
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openEdit(null)">{{ smAndUp ? t.wardrobe.newPiece : t.common.create }}</v-btn>
    </div>

    <v-chip-group v-if="showOwners" v-model="owner" mandatory selected-class="text-primary" class="mb-2">
      <v-chip value="" variant="outlined" size="default" prepend-icon="mdi-account-group-outline" filter>{{ t.wardrobe.everyone }}</v-chip>
      <v-chip v-for="p in catalog.people" :key="p.id" :value="p.id" variant="outlined" size="default" filter>
        <template #prepend>
          <v-avatar size="20" class="mr-1" :image="p.picture ?? undefined" color="primary" variant="tonal">
            <span v-if="!p.picture" class="text-caption">{{ p.name.charAt(0) }}</span>
          </v-avatar>
        </template>
        {{ p.name }}
      </v-chip>
    </v-chip-group>

    <v-alert v-if="error" type="error" variant="tonal" :text="error" class="mb-4">
      <template #append><v-btn variant="text" @click="reload">{{ t.app.retry }}</v-btn></template>
    </v-alert>

    <v-row dense class="mb-2">
      <v-col v-if="laundryPrompt" cols="12">
        <LaundryPromptBanner :prompt="laundryPrompt" :pieces="laundry" @changed="reloadSummary" />
      </v-col>
      <!-- Today's outfit with "Suggest an outfit" -->
      <v-col cols="12" :lg="laundry.length ? 8 : 12">
        <TodayOutfitCard :outfits="outfits" :garments="byId" :owner="ownerParam" @changed="reloadOutfits" />
      </v-col>

      <v-col v-if="laundry.length" cols="12" lg="4">
        <v-card variant="flat" border class="h-100 d-flex flex-column">
          <v-card-item>
            <template #prepend><v-avatar color="warning" variant="tonal"><v-icon icon="mdi-washing-machine" /></v-avatar></template>
            <v-card-title class="text-subtitle-1 font-weight-medium">{{ t.wardrobe.laundry }}</v-card-title>
            <v-card-subtitle class="text-wrap">{{ t.wardrobe.inLaundry(laundry.length) }}</v-card-subtitle>
            <template v-if="!lgAndUp" #append>
              <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-check-all" :loading="washing" @click="doLaundry">{{ t.wardrobe.laundryDone }}</v-btn>
            </template>
          </v-card-item>
          <template v-if="lgAndUp">
            <div class="d-flex flex-wrap ga-1 px-4">
              <div v-for="g in laundry.slice(0, 8)" :key="g.id" class="clickable" style="width: 40px" :title="g.name" @click="openDetail(g)">
                <GarmentThumb :photo-id="g.photo_id" :layer="g.layer" :icon-size="18" rounded="md" />
              </div>
              <div v-if="laundry.length > 8" class="text-caption text-medium-emphasis align-self-center ml-1">+{{ laundry.length - 8 }}</div>
            </div>
            <v-spacer />
            <v-card-actions class="px-4 pb-3">
              <v-btn color="primary" variant="tonal" prepend-icon="mdi-check-all" :loading="washing" @click="doLaundry">{{ t.wardrobe.laundryDone }}</v-btn>
            </v-card-actions>
          </template>
        </v-card>
      </v-col>
    </v-row>

    <div class="d-flex align-center mb-3">
      <v-tabs v-model="tab" color="primary">
        <v-tab value="closet" prepend-icon="mdi-wardrobe-outline">{{ t.wardrobe.closet }}</v-tab>
        <v-tab value="outfits" prepend-icon="mdi-view-grid-outline">{{ t.wardrobe.outfits }}<span class="ml-1 text-medium-emphasis">{{ outfits.length }}</span></v-tab>
      </v-tabs>
      <v-spacer />
      <v-btn
        v-if="tab === 'closet'"
        :variant="selecting ? 'flat' : 'tonal'"
        :color="selecting ? 'primary' : undefined"
        size="small"
        class="flex-shrink-0"
        :prepend-icon="selecting ? 'mdi-close' : 'mdi-checkbox-multiple-marked-outline'"
        @click="selecting ? stopSelecting() : (selecting = true)"
      >
        {{ selecting ? t.wardrobe.cancelSelect : t.wardrobe.select }}
      </v-btn>
    </div>

    <v-window v-model="tab" :touch="false">
      <!-- Closet -->
      <v-window-item value="closet">
        <v-row dense class="mb-1">
          <v-col cols="12" md="6">
            <v-text-field v-model="search" :placeholder="t.wardrobe.searchPlaceholder" prepend-inner-icon="mdi-magnify" clearable hide-details density="compact" variant="solo-filled" flat rounded="pill" />
          </v-col>
          <v-col cols="12" md="6" class="d-flex align-center">
            <div class="d-flex ga-2 overflow-x-auto filter-row flex-grow-1 min-w-0">
              <v-menu v-for="f in filterMenus" :key="f.key">
                <template #activator="{ props }">
                  <v-chip v-bind="props" :color="f.model.value ? 'primary' : undefined" :variant="f.model.value ? 'tonal' : 'outlined'" size="default" :prepend-icon="f.icon" append-icon="mdi-menu-down" class="flex-shrink-0">
                    {{ f.model.value ? f.items.find((i) => i.value === f.model.value)?.title : f.title }}
                  </v-chip>
                </template>
                <v-list density="compact">
                  <v-list-item :title="f.any" :active="!f.model.value" @click="f.model.value = null" />
                  <v-divider />
                  <v-list-item v-for="i in f.items" :key="i.value" :title="i.title" :active="f.model.value === i.value" @click="f.model.value = i.value" />
                </v-list>
              </v-menu>
              <v-chip :color="favorites ? 'error' : undefined" :variant="favorites ? 'tonal' : 'outlined'" size="default" :prepend-icon="favorites ? 'mdi-heart' : 'mdi-heart-outline'" class="flex-shrink-0" @click="favorites = !favorites">
                {{ t.wardrobe.favorites }}
              </v-chip>
            </div>
          </v-col>
        </v-row>

        <v-chip-group v-model="layer" mandatory selected-class="text-primary" class="mb-2">
          <v-chip value="all" variant="outlined" size="default" filter>
            {{ t.wardrobe.allLayers }}<span class="ml-1 text-medium-emphasis">{{ matching.length }}</span>
          </v-chip>
          <v-chip v-for="l in layers" :key="l" :value="l" variant="outlined" size="default" :prepend-icon="layerIcon[l]" :disabled="!layerCounts[l] && layer !== l">
            {{ label.layer(l) }}<span class="ml-1 text-medium-emphasis">{{ layerCounts[l] ?? 0 }}</span>
          </v-chip>
        </v-chip-group>

        <v-row v-if="loading && !garments.length" dense>
          <v-col v-for="i in 12" :key="i" cols="6" sm="4" md="3" lg="2"><v-skeleton-loader type="image, list-item" class="rounded-xl" /></v-col>
        </v-row>

        <EmptyState v-else-if="!visibleCount" icon="mdi-hanger" :title="t.wardrobe.empty" :text="garments.length ? undefined : t.wardrobe.emptyHint">
          <v-btn v-if="garments.length && filtersActive" variant="tonal" prepend-icon="mdi-filter-off-outline" @click="resetFilters">{{ t.wardrobe.clearFilters }}</v-btn>
          <v-btn v-else color="primary" variant="tonal" prepend-icon="mdi-plus" @click="openEdit(null)">{{ t.wardrobe.newPiece }}</v-btn>
        </EmptyState>

        <template v-else>
          <section v-for="grp in groups" :key="grp.layer" class="mb-5">
            <div v-if="layer === 'all'" class="d-flex align-center text-subtitle-1 font-weight-medium mb-2">
              <v-icon :icon="layerIcon[grp.layer] ?? 'mdi-hanger'" size="20" class="mr-2 text-medium-emphasis" />
              {{ label.layer(grp.layer) || t.common.more }}
              <span class="text-caption text-medium-emphasis ml-2">{{ grp.items.length }}</span>
            </div>
            <v-row dense>
              <v-col v-for="g in grp.items" :key="g.id" cols="6" sm="4" md="3" lg="2">
                <v-card
                  variant="flat"
                  border
                  class="garment-card h-100"
                  :class="{ 'garment-card--selected': selected.includes(g.id), 'garment-card--away': !available(g) }"
                  @click="onCard(g)"
                >
                  <div class="pa-2 pb-0 position-relative">
                    <GarmentThumb :photo-id="g.photo_id" :layer="g.layer" class="garment-card__img" />
                    <v-icon v-if="g.favorite" icon="mdi-heart" color="error" size="18" class="garment-card__fav" />
                    <v-chip v-if="g.state !== 'clean'" :color="stateColor[g.state]" :prepend-icon="stateIcon[g.state]" variant="flat" size="x-small" class="garment-card__state">
                      {{ label.state(g.state) }}
                    </v-chip>
                    <v-icon v-if="selecting" :icon="selected.includes(g.id) ? 'mdi-check-circle' : 'mdi-circle-outline'" :color="selected.includes(g.id) ? 'primary' : undefined" size="24" class="garment-card__check" />
                  </div>
                  <div class="px-3 pt-2 pb-3">
                    <div class="text-body-2 font-weight-medium text-truncate">{{ g.name }}</div>
                    <div class="text-caption text-medium-emphasis text-truncate">
                      {{ label.category(g.category) }}<template v-if="showOwners && g.owner"> · {{ personName(g.owner) }}</template>
                    </div>
                  </div>
                </v-card>
              </v-col>
            </v-row>
          </section>
        </template>
      </v-window-item>

      <!-- Outfits -->
      <v-window-item value="outfits">
        <EmptyState v-if="!outfits.length" icon="mdi-view-grid-outline" :title="t.wardrobe.noOutfits" :text="t.wardrobe.noOutfitsHint">
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-checkbox-multiple-marked-outline" @click="tab = 'closet'; selecting = true">{{ t.wardrobe.select }}</v-btn>
        </EmptyState>
        <v-row v-else dense>
          <v-col v-for="o in outfits" :key="o.id" cols="12" sm="6" md="4" lg="3">
            <v-card variant="flat" border class="h-100 d-flex flex-column">
              <div class="pa-3 pb-0"><OutfitCollage :ids="o.garment_ids" :garments="byId" :row="xs" :max="xs ? 4 : 6" :tile="80" /></div>
              <v-card-item class="pb-1">
                <v-card-title class="text-subtitle-1 font-weight-medium">{{ outfitDay(o) }}</v-card-title>
                <v-card-subtitle>
                  <v-icon :icon="sourceIcon[o.source] ?? 'mdi-hanger'" size="14" class="mr-1" />{{ label.source(o.source) }}<template v-if="o.occasion"> · {{ label.use(o.occasion) }}</template>
                  <template v-if="showOwners && o.owner"> · {{ personName(o.owner) }}</template>
                </v-card-subtitle>
              </v-card-item>
              <v-card-text v-if="o.reason" class="py-1 text-body-2">{{ o.reason }}</v-card-text>
              <v-spacer />
              <v-card-actions class="px-3">
                <v-chip v-if="o.worn" color="success" variant="tonal" prepend-icon="mdi-check" label>{{ t.wardrobe.worn }}</v-chip>
                <v-btn v-else color="primary" variant="tonal" size="small" prepend-icon="mdi-tshirt-crew" @click="wearOutfit(o)">{{ t.wardrobe.wear }}</v-btn>
                <v-spacer />
                <v-btn :icon="o.rating === 1 ? 'mdi-thumb-up' : 'mdi-thumb-up-outline'" :color="o.rating === 1 ? 'success' : undefined" size="small" variant="text" :title="t.wardrobe.liked" @click="rate(o, 1)" />
                <v-btn :icon="o.rating === -1 ? 'mdi-thumb-down' : 'mdi-thumb-down-outline'" :color="o.rating === -1 ? 'error' : undefined" size="small" variant="text" :title="t.wardrobe.disliked" @click="rate(o, -1)" />
                <v-btn icon="mdi-delete-outline" size="small" variant="text" :title="t.wardrobe.deleteOutfit" @click="deleteOutfitFor = o; confirmOutfit = true" />
              </v-card-actions>
            </v-card>
          </v-col>
        </v-row>
      </v-window-item>
    </v-window>

    <!-- Selection bar -->
    <v-slide-y-reverse-transition>
      <div v-if="selecting" class="select-bar">
        <v-card color="surface-container" elevation="6" rounded="pill" class="d-flex align-center pa-2 pl-5 ga-2">
          <span class="text-body-2 font-weight-medium text-no-wrap">{{ t.wardrobe.selected(selected.length) }}</span>
          <v-spacer />
          <v-btn variant="text" :disabled="!selected.length" :icon="!mdAndUp" :title="t.wardrobe.saveOutfit" @click="openSaveOutfit">
            <v-icon icon="mdi-content-save-outline" />
            <span v-if="mdAndUp" class="ml-2">{{ t.wardrobe.saveOutfit }}</span>
          </v-btn>
          <v-btn color="primary" variant="flat" rounded="pill" prepend-icon="mdi-tshirt-crew" :disabled="!selected.length" @click="wearSelected">{{ t.wardrobe.wearToday }}</v-btn>
          <v-btn icon="mdi-close" variant="text" size="small" :title="t.wardrobe.cancelSelect" @click="stopSelecting" />
        </v-card>
      </div>
    </v-slide-y-reverse-transition>

    <v-dialog v-model="outfitDialog" max-width="440">
      <v-card :title="t.wardrobe.saveOutfit" prepend-icon="mdi-content-save-outline">
        <v-card-text>
          <OutfitCollage :ids="selected" :garments="byId" row :max="6" :tile="72" class="mb-4" />
          <v-select
            v-model="outfitForm.occasion"
            :items="occasionItems"
            :label="t.wardrobe.occasion"
            clearable
          />
          <v-switch v-model="outfitForm.worn" :label="t.wardrobe.wearingToday" color="primary" inset hide-details />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="outfitDialog = false">{{ t.common.cancel }}</v-btn>
          <v-btn color="primary" variant="flat" :loading="savingOutfit" @click="saveOutfit">{{ t.common.save }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <GarmentSheet v-model="detailOpen" :garment="detail" @edit="(g) => openEdit(g)" />
    <GarmentDialog v-model="editOpen" :garment="editFor" :default-owner="ownerParam" />
    <StyleProfileDialog v-model="profileOpen" :owner="ownerParam" :owner-name="ownerParam ? personName(ownerParam) : null" />
    <ConfirmDialog v-model="confirmOutfit" :title="t.wardrobe.deleteOutfit" :text="t.wardrobe.confirmDeleteOutfit" @confirm="removeOutfit" />
  </div>
</template>

<style scoped>
.filter-row {
  scrollbar-width: none;
  padding: 2px 0;
}
.filter-row::-webkit-scrollbar {
  display: none;
}
.garment-card {
  transition: border-color 0.15s, box-shadow 0.15s;
}
.garment-card--selected {
  border-color: rgb(var(--v-theme-primary)) !important;
  box-shadow: 0 0 0 1px rgb(var(--v-theme-primary)) inset;
}
.garment-card--away .garment-card__img {
  opacity: 0.55;
}
.garment-card__fav {
  position: absolute;
  top: 14px;
  right: 14px;
}
.garment-card__check {
  position: absolute;
  top: 12px;
  left: 12px;
  background: rgb(var(--v-theme-surface));
  border-radius: 50%;
}
.garment-card__state {
  position: absolute;
  left: 14px;
  bottom: 6px;
  max-width: calc(100% - 28px);
}
.select-bar {
  position: fixed;
  left: calc(var(--v-layout-left, 0px) + 12px);
  right: calc(var(--v-layout-right, 0px) + 12px);
  bottom: calc(var(--v-layout-bottom, 0px) + 12px);
  max-width: 680px;
  margin: 0 auto;
  z-index: 5;
}
.pb-selecting {
  padding-bottom: 96px;
}
</style>
