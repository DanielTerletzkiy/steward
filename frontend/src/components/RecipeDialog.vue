<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { api, fileUrl } from '@/api'
import { LOCALE, t } from '@/i18n'
import { useCatalog } from '@/composables/catalog'
import { attempt, notify } from '@/composables/notify'
import PhotoPicker from './PhotoPicker.vue'
import type { IngredientIn, Recipe, RecipeIn } from '@/types'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ recipe?: Recipe | null; allTags?: string[] }>()
const emit = defineEmits<{ saved: [Recipe] }>()
const { xs } = useDisplay()
const { state, productsById } = useCatalog()

interface Row {
  key: number
  text: string
  product_id: number | null
  stock_amount: string | number
  optional: boolean
  group: string | null
}
let nextKey = 1
const row = (r: Partial<Row> = {}): Row => ({ key: nextKey++, text: '', product_id: null, stock_amount: '', optional: false, group: null, ...r })

const form = ref({ name: '', description: '', servings: 2 as number | string, minutes: '' as number | string, tags: [] as string[], favorite: false, source_url: '', instructions: '' })
const rows = ref<Row[]>([row()])
const photo = ref<File | null>(null)
const removePhoto = ref(false)
const busy = ref(false)
const isEdit = computed(() => !!props.recipe)
const requiredRule = [(v: string | null) => !!v?.trim() || t.common.required]

watch(open, (v) => {
  if (!v) return
  photo.value = null
  removePhoto.value = false
  const r = props.recipe
  if (!r) {
    form.value = { name: '', description: '', servings: 2, minutes: '', tags: [], favorite: false, source_url: '', instructions: '' }
    rows.value = [row(), row(), row()]
    return
  }
  form.value = {
    name: r.name,
    description: r.description ?? '',
    servings: r.servings,
    minutes: r.minutes ?? '',
    tags: [...r.tags],
    favorite: r.favorite,
    source_url: r.source_url ?? '',
    instructions: r.instructions ?? '',
  }
  rows.value = r.ingredients.map((i) => row({ text: i.text, product_id: i.product_id, stock_amount: i.stock_amount ?? '', optional: i.optional, group: i.group }))
  if (!rows.value.length) rows.value = [row()]
})

const productItems = computed(() => state.products.map((p) => ({ value: p.id, title: p.name, subtitle: p.unit })))
const tagItems = computed(() => [...new Set(props.allTags ?? [])].sort((a, b) => a.localeCompare(b, LOCALE)))

function addRow() {
  rows.value.push(row())
}
function removeRow(r: Row) {
  rows.value = rows.value.filter((x) => x.key !== r.key)
}

// Paste many lines at once (or paste into a row: several lines split into rows).
const pasteOpen = ref(false)
const pasteText = ref('')
function addLines(text: string, after?: Row) {
  const lines = text.split(/\r?\n/).map((l) => l.replace(/^\s*[-*•]\s*/, '').trim()).filter(Boolean)
  if (!lines.length) return
  const fresh = lines.map((text) => row({ text }))
  const kept = rows.value.filter((r) => r.text.trim() || r === after)
  const i = after ? kept.indexOf(after) : -1
  if (after && !after.text.trim()) kept.splice(i, 1, ...fresh)
  else if (i >= 0) kept.splice(i + 1, 0, ...fresh)
  else kept.push(...fresh)
  rows.value = kept
}
function onPaste(e: ClipboardEvent, r: Row) {
  const text = e.clipboardData?.getData('text') ?? ''
  if (!text.includes('\n')) return
  e.preventDefault()
  addLines(text, r)
}

const num = (v: string | number | null | undefined) => {
  if (v === '' || v == null) return null
  const n = Number(String(v).replace(',', '.'))
  return Number.isFinite(n) ? n : null
}

async function save() {
  const f = form.value
  if (!f.name.trim()) return
  busy.value = true
  const ingredients: IngredientIn[] = rows.value
    .filter((r) => r.text.trim())
    .map((r) => ({ text: r.text.trim(), product_id: r.product_id, stock_amount: r.product_id ? num(r.stock_amount) : null, optional: r.optional, group: r.group }))
  const body: RecipeIn = {
    name: f.name.trim(),
    description: f.description.trim() || null,
    servings: Math.min(50, Math.max(1, Math.round(num(f.servings) ?? 2))),
    minutes: num(f.minutes) != null ? Math.round(num(f.minutes)!) : null,
    instructions: f.instructions.trim() || null,
    source_url: f.source_url.trim() || null,
    tags: [...new Set(f.tags.map((x) => x.trim()).filter(Boolean))],
    favorite: f.favorite,
    ingredients,
  }
  let saved = await attempt(() => (props.recipe ? api.updateRecipe(props.recipe.id, body) : api.createRecipe(body)))
  if (saved && photo.value) {
    const withPhoto = await attempt(() => api.setRecipePhoto(saved!.id, photo.value!))
    if (withPhoto) saved = withPhoto
  } else if (saved && removePhoto.value && saved.photo_id) {
    const without = await attempt(() => api.deleteRecipePhoto(saved!.id))
    if (without) saved = without
  }
  busy.value = false
  if (saved) {
    notify(t.recipes.saved)
    emit('saved', saved)
    open.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" :fullscreen="xs" max-width="860" scrollable>
    <v-card :rounded="xs ? 0 : 'xl'">
      <v-toolbar color="transparent" density="comfortable">
        <v-btn icon="mdi-close" :title="t.common.close" @click="open = false" />
        <v-toolbar-title class="font-weight-medium">{{ isEdit ? t.recipes.editRecipe : t.recipes.newRecipe }}</v-toolbar-title>
        <template v-if="xs" #append>
          <v-btn color="primary" variant="flat" class="mr-2" :loading="busy" @click="save">{{ t.common.save }}</v-btn>
        </template>
      </v-toolbar>
      <v-divider />
      <v-card-text class="pt-4">
        <v-form @submit.prevent="save">
          <v-row>
            <v-col cols="12" sm="4">
              <PhotoPicker v-model="photo" :current-url="recipe?.photo_id && !removePhoto ? fileUrl(recipe.photo_id, true) : null" icon="mdi-silverware-fork-knife" :aspect="4 / 3" removable @remove="removePhoto = true" />
            </v-col>
            <v-col cols="12" sm="8">
              <v-text-field v-model="form.name" :label="t.common.name" :rules="requiredRule" />
              <v-row dense>
                <v-col cols="6"><v-text-field v-model="form.servings" :label="t.recipes.servings" type="number" min="1" max="50" prepend-inner-icon="mdi-account-multiple-outline" /></v-col>
                <v-col cols="6"><v-text-field v-model="form.minutes" :label="t.recipes.time" type="number" min="0" prepend-inner-icon="mdi-timer-outline" /></v-col>
              </v-row>
              <v-combobox v-model="form.tags" :items="tagItems" :label="t.recipes.tags" multiple chips closable-chips />
              <v-switch v-model="form.favorite" :label="t.recipes.favorite" color="error" inset hide-details density="compact" true-icon="mdi-heart" false-icon="mdi-heart-outline" />
            </v-col>
          </v-row>
          <v-textarea v-model="form.description" :label="t.recipes.description" rows="2" auto-grow class="mt-2" />

          <div class="d-flex align-center mt-2 mb-2">
            <div class="text-subtitle-1 font-weight-medium">{{ t.recipes.ingredients }}</div>
            <v-spacer />
            <v-btn variant="text" size="small" prepend-icon="mdi-content-paste" @click="pasteText = ''; pasteOpen = true">{{ t.recipes.pasteMany }}</v-btn>
          </div>
          <v-sheet v-for="r in rows" :key="r.key" color="surface-container" rounded="lg" class="pa-2 mb-2">
            <div class="d-flex align-center ga-1">
              <v-text-field
                v-model="r.text"
                :placeholder="t.recipes.ingredientPlaceholder"
                density="compact"
                hide-details
                variant="solo-filled"
                flat
                bg-color="surface"
                @paste="(e: ClipboardEvent) => onPaste(e, r)"
              />
              <v-btn icon="mdi-close" variant="text" size="small" :title="t.common.delete" @click="removeRow(r)" />
            </div>
            <v-row dense class="mt-1">
              <v-col cols="12" sm="6">
                <v-autocomplete
                  v-model="r.product_id"
                  :items="productItems"
                  :label="t.recipes.linkProduct"
                  density="compact"
                  hide-details
                  clearable
                  prepend-inner-icon="mdi-link-variant"
                  bg-color="surface"
                />
              </v-col>
              <v-col cols="7" sm="4">
                <v-text-field
                  v-model="r.stock_amount"
                  :label="t.recipes.usesPerBatch"
                  :placeholder="t.recipes.usesHint"
                  :suffix="r.product_id ? productsById.get(r.product_id)?.unit : undefined"
                  :disabled="!r.product_id"
                  density="compact"
                  hide-details
                  inputmode="decimal"
                  bg-color="surface"
                />
              </v-col>
              <v-col cols="5" sm="2" class="d-flex align-center">
                <v-checkbox v-model="r.optional" :label="t.recipes.optional" density="compact" hide-details />
              </v-col>
            </v-row>
          </v-sheet>
          <v-btn variant="tonal" size="small" prepend-icon="mdi-plus" class="mb-4" @click="addRow">{{ t.recipes.addIngredient }}</v-btn>

          <v-textarea v-model="form.instructions" :label="t.recipes.instructions" :hint="t.recipes.instructionsHint" persistent-hint rows="5" auto-grow />
          <v-text-field v-model="form.source_url" :label="t.recipes.source" prepend-inner-icon="mdi-link-variant" inputmode="url" class="mt-3" />
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

    <v-dialog v-model="pasteOpen" max-width="480">
      <v-card :title="t.recipes.pasteTitle" prepend-icon="mdi-content-paste">
        <v-card-text>
          <v-textarea v-model="pasteText" :hint="t.recipes.pasteHint" persistent-hint rows="8" autofocus />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="pasteOpen = false">{{ t.common.cancel }}</v-btn>
          <v-btn color="primary" variant="flat" @click="addLines(pasteText); pasteOpen = false">{{ t.recipes.pasteAdd }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-dialog>
</template>
