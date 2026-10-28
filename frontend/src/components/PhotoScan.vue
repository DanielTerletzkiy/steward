<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { useCatalog } from '@/composables/catalog'
import { attempt, notify } from '@/composables/notify'
import { addDays, todayIso } from '@/composables/format'
import { aiProblem, type AiProblem } from '@/composables/aiErrors'
import { runScanAction } from '@/composables/scanActions'
import AiProblemAlert from './AiProblemAlert.vue'
import EmptyState from './EmptyState.vue'
import type { Product, RecognizedItem } from '@/types'

const { state, productsById, categories, units } = useCatalog()

const MAX = 3
const photos = ref<{ file: File; url: string }[]>([])
const hint = ref('')
const cameraInput = ref<HTMLInputElement | null>(null)
const galleryInput = ref<HTMLInputElement | null>(null)

function picked(e: Event) {
  const input = e.target as HTMLInputElement
  for (const file of Array.from(input.files ?? [])) {
    if (photos.value.length >= MAX) break
    photos.value.push({ file, url: URL.createObjectURL(file) })
  }
  input.value = ''
}
function removePhoto(i: number) {
  URL.revokeObjectURL(photos.value[i].url)
  photos.value.splice(i, 1)
}
onBeforeUnmount(() => photos.value.forEach((p) => URL.revokeObjectURL(p.url)))

interface Row {
  item: RecognizedItem
  include: boolean
  productId: number | null
  createNew: boolean
  name: string
  category: string | null
  unit: string
  amount: number | string
  dueDate: string | null
  locationId: number | null
}
const rows = ref<Row[]>([])
const busy = ref(false)
const recognized = ref(false)
const problem = ref<AiProblem | null>(null)

async function recognize() {
  if (!photos.value.length) return
  busy.value = true
  problem.value = null
  try {
    const res = await api.scanPhoto(
      photos.value.map((p) => p.file),
      hint.value.trim() || null,
    )
    rows.value = res.items.map((item) => {
      const product = item.product_id != null ? productsById.value.get(item.product_id) : undefined
      return {
        item,
        include: true,
        productId: item.product_id,
        createNew: item.product_id == null,
        name: item.name,
        category: item.category,
        unit: product?.unit ?? (item.unit === 'pc' ? 'Stk' : item.unit),
        amount: item.quantity || 1,
        dueDate: item.due_date ?? (item.shelf_life_days ? addDays(todayIso(), item.shelf_life_days) : product?.due_days != null ? addDays(todayIso(), product.due_days) : null),
        locationId: item.location_id ?? product?.location_id ?? null,
      }
    })
    recognized.value = true
  } catch (e) {
    problem.value = aiProblem(e)
  } finally {
    busy.value = false
  }
}

const included = computed(() => rows.value.filter((r) => r.include && (r.createNew ? r.name.trim() : r.productId != null)))
const adding = ref(false)

async function addAll() {
  adding.value = true
  let added = 0
  for (const r of included.value) {
    let product: Product | undefined | null = r.createNew ? null : productsById.value.get(r.productId!)
    if (!product) {
      product = await attempt(() =>
        api.createProduct({
          name: r.name.trim(),
          brand: r.item.brand,
          category: r.category || null,
          location_id: r.locationId,
          unit: r.unit || 'Stk',
          due_days: r.item.shelf_life_days ?? null,
          barcodes: r.item.barcode ? [r.item.barcode] : [],
        }),
      )
      if (!product) continue
    }
    const n = Number(String(r.amount).replace(',', '.'))
    const ok = await runScanAction(product, 'purchase', Number.isFinite(n) && n > 0 ? n : 1, { dueDate: r.dueDate })
    if (ok) {
      added++
      r.include = false
    }
  }
  adding.value = false
  if (added) {
    notify(t.scan.addedAll(added))
    rows.value = rows.value.filter((r) => r.include)
  }
}

function reset() {
  photos.value.forEach((p) => URL.revokeObjectURL(p.url))
  photos.value = []
  rows.value = []
  recognized.value = false
  hint.value = ''
}
</script>

<template>
  <div>
    <v-card variant="flat" border class="mb-4">
      <v-card-text>
        <div class="text-body-2 text-medium-emphasis mb-3">{{ t.scan.photoIntro }}</div>
        <div class="photo-grid mb-3">
          <div v-for="(p, i) in photos" :key="p.url" class="photo-tile">
            <v-img :src="p.url" cover :aspect-ratio="1" class="rounded-lg" />
            <v-btn icon="mdi-close" size="x-small" variant="flat" color="surface" class="photo-remove" :title="t.common.delete" @click="removePhoto(i)" />
          </div>
          <v-sheet
            v-if="photos.length < MAX"
            color="surface-container"
            rounded="lg"
            class="photo-tile d-flex flex-column align-center justify-center clickable text-medium-emphasis"
            @click="cameraInput?.click()"
          >
            <v-icon icon="mdi-camera-plus-outline" size="32" class="mb-1" />
            <span class="text-caption">{{ t.scan.addPhoto }}</span>
          </v-sheet>
        </div>
        <div class="d-flex flex-wrap ga-2 mb-3">
          <v-btn variant="tonal" color="primary" prepend-icon="mdi-camera-outline" :disabled="photos.length >= MAX" @click="cameraInput?.click()">{{ t.wardrobe.takePhoto }}</v-btn>
          <v-btn variant="tonal" prepend-icon="mdi-image-multiple-outline" :disabled="photos.length >= MAX" @click="galleryInput?.click()">{{ t.wardrobe.choosePhoto }}</v-btn>
          <span class="text-caption text-medium-emphasis align-self-center">{{ t.scan.maxPhotos }}</span>
        </div>
        <input ref="cameraInput" type="file" accept="image/*" capture="environment" hidden @change="picked" />
        <input ref="galleryInput" type="file" accept="image/*" multiple hidden @change="picked" />
        <v-text-field v-model="hint" :label="t.scan.hint" :placeholder="t.scan.hintPlaceholder" persistent-placeholder hide-details class="mb-3" />
        <v-btn color="primary" variant="flat" size="large" block prepend-icon="mdi-creation" :disabled="!photos.length" :loading="busy" @click="recognize">{{ t.scan.recognize }}</v-btn>
        <v-expand-transition>
          <div v-if="busy" class="mt-3">
            <v-progress-linear indeterminate color="primary" rounded class="mb-2" />
            <div class="text-body-2">{{ t.scan.recognizing }}</div>
            <div class="text-caption text-medium-emphasis">{{ t.scan.recognizingHint }}</div>
          </div>
        </v-expand-transition>
        <AiProblemAlert v-if="problem" :problem="problem" class="mt-3" @close="problem = null" />
      </v-card-text>
    </v-card>

    <template v-if="recognized">
      <EmptyState v-if="!rows.length" compact icon="mdi-image-search-outline" :title="t.scan.noItems" />
      <v-card v-for="(r, i) in rows" :key="i" variant="flat" border class="mb-3" :class="{ 'opacity-60': !r.include }">
        <v-card-item>
          <template #prepend><v-checkbox-btn v-model="r.include" color="primary" :title="t.scan.include" /></template>
          <v-card-title class="text-subtitle-1 font-weight-medium" style="white-space: normal">{{ r.item.name }}</v-card-title>
          <v-card-subtitle>
            <template v-if="r.item.brand">{{ r.item.brand }} · </template>
            <span v-if="r.item.confidence != null">{{ t.scan.confidence(Math.round((r.item.confidence <= 1 ? r.item.confidence * 100 : r.item.confidence))) }}</span>
          </v-card-subtitle>
        </v-card-item>
        <v-card-text v-if="r.include" class="pt-0">
          <v-switch v-model="r.createNew" :label="t.scan.newProduct" color="primary" density="compact" hide-details inset class="mb-2" />
          <v-autocomplete
            v-if="!r.createNew"
            v-model="r.productId"
            :items="state.products"
            item-title="name"
            item-value="id"
            :label="t.scan.match"
            prepend-inner-icon="mdi-link-variant"
            auto-select-first
          />
          <v-row v-else dense>
            <v-col cols="12" sm="6"><v-text-field v-model="r.name" :label="t.common.name" /></v-col>
            <v-col cols="6" sm="3"><v-combobox v-model="r.category" :items="categories" :label="t.common.category" /></v-col>
            <v-col cols="6" sm="3"><v-combobox v-model="r.unit" :items="units" :label="t.common.unit" /></v-col>
          </v-row>
          <v-row dense>
            <v-col cols="4" sm="3"><v-text-field v-model="r.amount" :label="t.scan.amount" type="number" min="0" step="any" /></v-col>
            <v-col cols="8" sm="5">
              <v-text-field
                v-model="r.dueDate"
                type="date"
                :label="t.scan.dueDate"
                clearable
                :hint="r.item.date_text_seen ? t.scan.seen(r.item.date_text_seen) : undefined"
                persistent-hint
              />
            </v-col>
            <v-col cols="12" sm="4">
              <v-select v-model="r.locationId" :items="state.locations" item-title="name" item-value="id" :label="t.common.location" clearable />
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
      <div v-if="rows.length" class="d-flex flex-wrap ga-2">
        <v-btn color="primary" variant="flat" size="large" prepend-icon="mdi-fridge-variant-outline" :disabled="!included.length" :loading="adding" @click="addAll">
          {{ t.scan.addAll(included.length) }}
        </v-btn>
        <v-btn variant="text" size="large" @click="reset">{{ t.common.cancel }}</v-btn>
      </div>
    </template>
  </div>
</template>

<style scoped>
.photo-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 120px));
  gap: 8px;
}
.photo-tile {
  position: relative;
  aspect-ratio: 1;
}
.photo-remove {
  position: absolute;
  top: 4px;
  right: 4px;
}
</style>
