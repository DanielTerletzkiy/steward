<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { api, fileUrl } from '@/api'
import { LOCALE, t } from '@/i18n'
import { useCatalog } from '@/composables/catalog'
import { attempt, notify, notifyError } from '@/composables/notify'
import { label, swatch, useVocabulary } from '@/composables/wardrobe'
import PhotoPicker from './PhotoPicker.vue'
import AiProblemAlert from './AiProblemAlert.vue'
import { aiProblem, type AiProblem } from '@/composables/aiErrors'
import type { Garment, GarmentIn, LaundryMode } from '@/types'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ garment?: Garment | null; defaultOwner?: string | null }>()
const emit = defineEmits<{ saved: [Garment] }>()
const { xs } = useDisplay()
const { state } = useCatalog()
const vocab = useVocabulary()

const TEMP_MIN = -15
const TEMP_MAX = 35

const blank = () => ({
  name: '',
  category: null as string | null,
  colors: [] as string[],
  pattern: null as string | null,
  material: '',
  warmth: 3,
  temp: [5, 22] as number[],
  tempSet: false,
  rain: 'none',
  windproof: false,
  formality: 2,
  uses: [] as string[],
  seasons: [] as string[],
  brand: '',
  size: '',
  price: '' as string | number,
  favorite: false,
  notes: '',
  wears_per_wash: '' as string | number,
  laundry_mode: '__default' as LaundryMode | '__default',
  owner: null as string | null,
})
const form = ref(blank())
const photo = ref<File | null>(null)
const removePhoto = ref(false)
const careLabel = ref<File | null>(null)
const careInput = ref<HTMLInputElement | null>(null)
const analyzing = ref(false)
const problem = ref<AiProblem | null>(null)
const busy = ref(false)
const isEdit = computed(() => !!props.garment)

watch(open, (v) => {
  if (!v) return
  photo.value = null
  removePhoto.value = false
  careLabel.value = null
  problem.value = null
  const g = props.garment
  if (!g) {
    form.value = { ...blank(), owner: props.defaultOwner ?? null }
    return
  }
  const hasTemp = g.temp_min != null || g.temp_max != null
  form.value = {
    name: g.name,
    category: g.category,
    colors: [...g.colors],
    pattern: g.pattern,
    material: g.material ?? '',
    warmth: g.warmth,
    temp: hasTemp ? [g.temp_min ?? TEMP_MIN, g.temp_max ?? TEMP_MAX] : [5, 22],
    tempSet: hasTemp,
    rain: g.rain,
    windproof: g.windproof,
    formality: g.formality,
    uses: [...g.uses],
    seasons: [...g.seasons],
    brand: g.brand ?? '',
    size: g.size ?? '',
    price: g.price ?? '',
    favorite: g.favorite,
    notes: g.notes ?? '',
    wears_per_wash: g.wears_per_wash,
    laundry_mode: g.laundry_mode ?? '__default',
    owner: g.owner,
  }
})

const categoryInfo = computed(() => vocab.value?.categories.find((c) => c.name === form.value.category) ?? null)
const categoryItems = computed(() => {
  const v = vocab.value
  if (!v) return []
  const order = new Map(v.layers.map((l, i) => [l, i]))
  return [...v.categories]
    .sort((a, b) => (order.get(a.layer) ?? 99) - (order.get(b.layer) ?? 99) || label.category(a.name).localeCompare(label.category(b.name), LOCALE))
    .map((c) => ({ value: c.name, title: label.category(c.name), subtitle: label.layer(c.layer) }))
})
const patternItems = computed(() => (vocab.value?.patterns ?? []).map((p) => ({ value: p, title: label.pattern(p) })))
const laundryItems = computed(() => {
  const info = categoryInfo.value
  const fallback = info
    ? t.wardrobe.laundryModeDefault(label.category(info.name), t.wardrobe.laundryModes[info.laundry_mode])
    : t.wardrobe.laundryModeDefaultPlain
  return [{ value: '__default', title: fallback }, ...(vocab.value?.laundry_modes ?? ['auto', 'ask']).map((m) => ({ value: m, title: t.wardrobe.laundryModes[m] ?? m }))]
})
const ownerItems = computed(() => [{ value: null, title: t.wardrobe.household }, ...state.people.map((p) => ({ value: p.id, title: p.name }))])
const suggestedName = computed(() => {
  const f = form.value
  if (!f.category) return ''
  // "T-shirt · Black" reads fine in every language, unlike adjective forms.
  const cat = label.category(f.category)
  return f.colors[0] ? `${cat} · ${label.color(f.colors[0])}` : cat
})
const tempText = computed(() => (form.value.tempSet ? t.wardrobe.tempValue(form.value.temp[0], form.value.temp[1]) : t.wardrobe.tempAny))

function carePicked(e: Event) {
  const input = e.target as HTMLInputElement
  careLabel.value = input.files?.[0] ?? null
  input.value = ''
}

/** Let the AI look at the photo (and care label) and prefill the form; the user checks and saves. */
async function fillWithAi() {
  if (!photo.value) return
  analyzing.value = true
  problem.value = null
  try {
    const a = await api.analyzeGarment(careLabel.value ? [photo.value, careLabel.value] : [photo.value])
    const f = form.value
    if (a.category) f.category = a.category
    if (a.name) f.name = a.name
    if (a.colors.length) f.colors = [...a.colors]
    f.pattern = a.pattern ?? f.pattern
    f.material = a.material ?? f.material
    f.warmth = a.warmth
    if (a.temp_min != null || a.temp_max != null) {
      f.temp = [Math.max(TEMP_MIN, Math.round(a.temp_min ?? TEMP_MIN)), Math.min(TEMP_MAX, Math.round(a.temp_max ?? TEMP_MAX))]
      f.tempSet = true
    }
    f.rain = a.rain
    f.windproof = a.windproof
    f.formality = a.formality
    if (a.uses.length) f.uses = [...a.uses]
    if (a.seasons.length) f.seasons = [...a.seasons]
    f.brand = a.brand ?? f.brand
    if (a.wears_per_wash != null) f.wears_per_wash = a.wears_per_wash
    notify(t.wardrobe.filled)
  } catch (e) {
    problem.value = aiProblem(e)
  } finally {
    analyzing.value = false
  }
}

function num(v: string | number | null | undefined): number | null {
  if (v === null || v === undefined || v === '') return null
  const n = Number(String(v).replace(',', '.'))
  return Number.isFinite(n) ? n : null
}

async function save() {
  const f = form.value
  if (!f.category) {
    notifyError(new Error(`${t.wardrobe.category}: ${t.common.required}`))
    return
  }
  busy.value = true
  const wpw = num(f.wears_per_wash)
  const body: GarmentIn = {
    owner: f.owner,
    name: f.name.trim() || suggestedName.value,
    category: f.category,
    colors: f.colors,
    pattern: f.pattern || null,
    material: f.material.trim() || null,
    warmth: f.warmth,
    temp_min: f.tempSet ? f.temp[0] : null,
    temp_max: f.tempSet ? f.temp[1] : null,
    rain: f.rain,
    windproof: f.windproof,
    formality: f.formality,
    uses: f.uses,
    seasons: f.seasons,
    brand: f.brand.trim() || null,
    size: f.size.trim() || null,
    price: num(f.price),
    favorite: f.favorite,
    notes: f.notes.trim() || null,
    laundry_mode: f.laundry_mode === '__default' ? null : f.laundry_mode,
    wears_per_wash: wpw == null ? (isEdit.value ? categoryInfo.value?.wears_per_wash ?? null : null) : Math.max(0, Math.round(wpw)),
  }
  if (body.wears_per_wash == null) delete body.wears_per_wash
  let saved = await attempt(() => (props.garment ? api.updateGarment(props.garment.id, body) : api.createGarment(body)))
  if (saved && photo.value) {
    const withPhoto = await attempt(() => api.setGarmentPhoto(saved!.id, photo.value!))
    if (withPhoto) saved = withPhoto
  } else if (saved && removePhoto.value && saved.photo_id) {
    const without = await attempt(() => api.deleteGarmentPhoto(saved!.id))
    if (without) saved = without
  }
  busy.value = false
  if (saved) {
    notify(t.wardrobe.pieceSaved)
    emit('saved', saved)
    open.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" :fullscreen="xs" max-width="760" scrollable>
    <v-card :rounded="xs ? 0 : 'xl'">
      <v-toolbar color="transparent" density="comfortable">
        <v-btn icon="mdi-close" :title="t.common.close" @click="open = false" />
        <v-toolbar-title class="font-weight-medium">{{ isEdit ? t.wardrobe.editPiece : t.wardrobe.newPiece }}</v-toolbar-title>
        <template v-if="xs" #append>
          <v-btn color="primary" variant="flat" class="mr-2" :loading="busy" @click="save">{{ t.common.save }}</v-btn>
        </template>
      </v-toolbar>
      <v-divider />
      <v-card-text class="pt-4">
        <v-form @submit.prevent="save">
          <v-row>
            <v-col cols="12" sm="5">
              <PhotoPicker v-model="photo" :current-url="garment?.photo_id && !removePhoto ? fileUrl(garment.photo_id) : null" contain icon="mdi-hanger" :aspect="xs ? 4 / 3 : 1" removable @remove="removePhoto = true" />
              <div v-if="photo" class="mt-3">
                <v-btn block color="primary" variant="flat" prepend-icon="mdi-creation" :loading="analyzing" @click="fillWithAi">{{ t.wardrobe.fillAi }}</v-btn>
                <v-btn block variant="text" size="small" class="mt-1" :prepend-icon="careLabel ? 'mdi-check' : 'mdi-tag-text-outline'" @click="careInput?.click()">
                  {{ careLabel ? careLabel.name : t.wardrobe.addCareLabel }}
                </v-btn>
                <input ref="careInput" type="file" accept="image/*" hidden @change="carePicked" />
                <div v-if="analyzing" class="text-caption text-medium-emphasis text-center">{{ t.wardrobe.filling }}</div>
              </div>
              <div v-else-if="!isEdit" class="text-caption text-medium-emphasis mt-2 d-flex align-center">
                <v-icon icon="mdi-creation" size="14" class="mr-1" />{{ t.wardrobe.aiPhotoHint }}
              </div>
              <AiProblemAlert v-if="problem" :problem="problem" class="mt-3" @close="problem = null" />
            </v-col>
            <v-col cols="12" sm="7">
              <v-autocomplete
                v-model="form.category"
                :items="categoryItems"
                :label="t.wardrobe.category"
                :hint="categoryInfo ? t.wardrobe.layerHint(label.layer(categoryInfo.layer), categoryInfo.wears_per_wash) : undefined"
                persistent-hint
                class="mb-3"
                auto-select-first
              >
                <template #item="{ props: itemProps, item }">
                  <v-list-item v-bind="itemProps" :subtitle="item.raw.subtitle" />
                </template>
              </v-autocomplete>
              <v-text-field v-model="form.name" :label="t.common.name" :placeholder="suggestedName" persistent-placeholder />
              <div class="text-caption text-medium-emphasis mb-1">{{ t.wardrobe.colors }}</div>
              <v-chip-group v-model="form.colors" multiple column selected-class="text-primary">
                <v-chip v-for="c in vocab?.colors ?? []" :key="c" :value="c" variant="outlined" filter>
                  <template #prepend>
                    <span class="swatch mr-1" :style="{ background: swatch(c) }" />
                  </template>
                  {{ label.color(c) }}
                </v-chip>
              </v-chip-group>
              <v-row dense class="mt-2">
                <v-col cols="6"><v-select v-model="form.pattern" :items="patternItems" :label="t.wardrobe.pattern" clearable /></v-col>
                <v-col cols="6"><v-text-field v-model="form.material" :label="t.wardrobe.material" :placeholder="t.wardrobe.materialHint" /></v-col>
              </v-row>
            </v-col>
          </v-row>

          <div class="text-subtitle-2 mt-2 mb-3 d-flex align-center"><v-icon icon="mdi-weather-partly-rainy" size="18" class="mr-2" />{{ t.wardrobe.weatherSection }}</div>
          <v-row dense>
            <v-col cols="12" sm="6">
              <div class="d-flex justify-space-between text-caption text-medium-emphasis">
                <span>{{ t.wardrobe.warmth }}</span><span class="text-primary font-weight-medium">{{ t.wardrobe.warmthLabels[form.warmth - 1] }}</span>
              </div>
              <v-slider v-model="form.warmth" :min="1" :max="5" :step="1" show-ticks="always" tick-size="4" color="primary" hide-details prepend-icon="mdi-snowflake" append-icon="mdi-fire" />
            </v-col>
            <v-col cols="12" sm="6">
              <div class="d-flex justify-space-between text-caption text-medium-emphasis">
                <span>{{ t.wardrobe.formality }}</span><span class="text-primary font-weight-medium">{{ t.wardrobe.formalityLabels[form.formality - 1] }}</span>
              </div>
              <v-slider v-model="form.formality" :min="1" :max="5" :step="1" show-ticks="always" tick-size="4" color="primary" hide-details prepend-icon="mdi-sofa-outline" append-icon="mdi-tie" />
            </v-col>
            <v-col cols="12" class="mt-2">
              <div class="d-flex justify-space-between align-center text-caption text-medium-emphasis">
                <span>{{ t.wardrobe.tempRange }}</span>
                <span class="d-flex align-center">
                  <span :class="form.tempSet ? 'text-primary font-weight-medium' : ''">{{ tempText }}</span>
                  <v-btn v-if="form.tempSet" size="x-small" variant="text" class="ml-1" @click="form.tempSet = false">{{ t.wardrobe.tempClear }}</v-btn>
                </span>
              </div>
              <v-range-slider
                v-model="form.temp"
                :min="TEMP_MIN"
                :max="TEMP_MAX"
                :step="1"
                :color="form.tempSet ? 'primary' : 'grey'"
                thumb-label
                hide-details
                strict
                prepend-icon="mdi-thermometer-low"
                append-icon="mdi-thermometer-high"
                @update:model-value="form.tempSet = true"
              />
            </v-col>
            <v-col cols="12" sm="8">
              <div class="text-caption text-medium-emphasis mb-1">{{ t.wardrobe.rain }}</div>
              <v-chip-group v-model="form.rain" mandatory selected-class="text-primary">
                <v-chip v-for="r in vocab?.rain ?? []" :key="r" :value="r" variant="outlined" filter>{{ label.rain(r) }}</v-chip>
              </v-chip-group>
            </v-col>
            <v-col cols="12" sm="4" class="d-flex align-end">
              <v-switch v-model="form.windproof" :label="t.wardrobe.windproof" color="primary" hide-details inset density="compact" />
            </v-col>
          </v-row>

          <div class="text-caption text-medium-emphasis mt-3 mb-1">{{ t.wardrobe.uses }}</div>
          <v-chip-group v-model="form.uses" multiple column selected-class="text-primary">
            <v-chip v-for="u in vocab?.uses ?? []" :key="u" :value="u" variant="outlined" filter>{{ label.use(u) }}</v-chip>
          </v-chip-group>
          <div class="text-caption text-medium-emphasis mt-2 mb-1">{{ t.wardrobe.seasons }}</div>
          <v-chip-group v-model="form.seasons" multiple column selected-class="text-primary">
            <v-chip v-for="s in vocab?.seasons ?? []" :key="s" :value="s" variant="outlined" filter>{{ label.season(s) }}</v-chip>
          </v-chip-group>

          <div class="text-subtitle-2 mt-5 mb-3 d-flex align-center"><v-icon icon="mdi-tag-outline" size="18" class="mr-2" />{{ t.wardrobe.detailsSection }}</div>
          <v-row dense>
            <v-col cols="12" sm="6"><v-text-field v-model="form.brand" :label="t.common.brand" /></v-col>
            <v-col cols="6" sm="3"><v-text-field v-model="form.size" :label="t.wardrobe.size" /></v-col>
            <v-col cols="6" sm="3"><v-text-field v-model="form.price" :label="t.common.price" inputmode="decimal" suffix="€" /></v-col>
            <v-col cols="12" :sm="state.people.length > 1 ? 6 : 12">
              <v-text-field
                v-model="form.wears_per_wash"
                :label="t.wardrobe.wearsPerWash"
                type="number"
                min="0"
                :placeholder="categoryInfo ? String(categoryInfo.wears_per_wash) : ''"
                :hint="categoryInfo ? t.wardrobe.wearsPerWashHint(categoryInfo.wears_per_wash) : undefined"
                persistent-hint
              />
            </v-col>
            <v-col cols="12">
              <v-select
                v-model="form.laundry_mode"
                :items="laundryItems"
                :label="t.wardrobe.laundryMode"
                :hint="t.wardrobe.laundryModeHint"
                persistent-hint
                prepend-inner-icon="mdi-basket-outline"
              />
            </v-col>
            <v-col v-if="state.people.length > 1" cols="12" sm="6">
              <v-select v-model="form.owner" :items="ownerItems" :label="t.wardrobe.owner" prepend-inner-icon="mdi-account-outline" />
            </v-col>
            <v-col cols="12">
              <v-switch v-model="form.favorite" :label="t.wardrobe.favorite" color="error" inset hide-details density="compact" true-icon="mdi-heart" false-icon="mdi-heart-outline" class="mb-2" />
            </v-col>
            <v-col cols="12"><v-textarea v-model="form.notes" :label="t.common.notes" rows="2" auto-grow /></v-col>
          </v-row>
          <button type="submit" hidden />
        </v-form>
      </v-card-text>
      <template v-if="!xs">
        <v-divider />
        <v-card-actions class="px-4">
          <v-spacer />
          <v-btn @click="open = false">{{ t.common.cancel }}</v-btn>
          <v-btn color="primary" variant="flat" :loading="busy" @click="save">{{ isEdit ? t.common.save : t.common.create }}</v-btn>
        </v-card-actions>
      </template>
    </v-card>
  </v-dialog>
</template>

