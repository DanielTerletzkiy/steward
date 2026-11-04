<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { api, fileUrl } from '@/api'
import { LOCALE, t } from '@/i18n'
import { useResource } from '@/composables/resource'
import { formatAmount, todayIso } from '@/composables/format'
import { statusColor, statusIcon } from '@/composables/recipes'
import { useKiosk } from '@/composables/kiosk'
import KioskInput from './KioskInput.vue'
import type { Fulfillment, MealPlanEntry, Recipe, RecipeSuggestion } from '@/types'

// Kiosk "Recipes" tab: today's meal plan and what can be cooked first; a recipe opens large enough to
// cook from across the kitchen, and keeps the screen on while it is open.
const kiosk = useKiosk()
const { data: suggestions } = useResource<RecipeSuggestion[]>(() => api.recipeSuggestions(200), ['recipes', 'stock'], [])
const { data: today } = useResource<MealPlanEntry[]>(() => api.mealPlan(todayIso(), todayIso()), ['mealplan'], [])

const filter = ref('')
const fold = (s: string) => s.toLocaleLowerCase(LOCALE).normalize('NFD').replace(/[̀-ͯ]/g, '')
const planned = computed(() => new Set(today.value.filter((m) => !m.done && m.recipe_id != null).map((m) => m.recipe_id!)))
const list = computed(() => {
  const q = fold(filter.value.trim())
  return suggestions.value
    .filter((s) => !q || fold(`${s.recipe.name} ${s.recipe.tags.join(' ')}`).includes(q))
    .sort((a, b) => Number(planned.value.has(b.recipe.id)) - Number(planned.value.has(a.recipe.id)) || b.score - a.score)
})

// --- one recipe ----------------------------------------------------------------

const openId = ref<number | null>(null)
const recipe = ref<Recipe | null>(null)
const fulfillment = ref<Fulfillment | null>(null)
async function load(id: number) {
  try {
    ;[recipe.value, fulfillment.value] = await Promise.all([api.recipe(id), api.fulfillment(id)])
  } catch (e) {
    kiosk.signal('error', e instanceof Error ? e.message : t.kiosk.failed)
    openId.value = null
  }
}
watch(openId, (id) => {
  recipe.value = null
  fulfillment.value = null
  kiosk.keepAwake.value = id != null
  if (id != null) load(id)
})
onBeforeUnmount(() => (kiosk.keepAwake.value = false))

const steps = computed(() => (recipe.value?.instructions ?? '').split(/\r?\n/).map((s) => s.trim()).filter(Boolean))
const statusById = computed(() => new Map((fulfillment.value?.ingredients ?? []).map((i) => [i.ingredient_id, i])))
const hasMissing = computed(() => (fulfillment.value?.ingredients ?? []).some((i) => i.status === 'missing' || i.status === 'partial'))

function submit() {
  if (list.value.length === 1) openId.value = list.value[0].recipe.id
}

const cookOpen = ref(false)
const busy = ref(false)
async function cook() {
  if (!recipe.value) return
  busy.value = true
  try {
    const res = await api.cook(recipe.value.id)
    cookOpen.value = false
    kiosk.signal('ok', `${t.recipes.cooked(recipe.value.name)} · ${t.recipes.usedN(res.used.length)}`)
    load(recipe.value.id)
  } catch (e) {
    kiosk.signal('error', e instanceof Error ? e.message : t.kiosk.failed)
  } finally {
    busy.value = false
  }
}
async function missingToList() {
  if (!recipe.value) return
  try {
    const res = await api.recipeToShopping(recipe.value.id)
    kiosk.signal('ok', t.recipes.addedToList(res.added.length))
  } catch (e) {
    kiosk.signal('error', e instanceof Error ? e.message : t.kiosk.failed)
  }
}
</script>

<template>
  <!-- A recipe, large -->
  <div v-if="openId != null">
    <div class="d-flex flex-wrap align-center ga-3 mb-4">
      <v-btn size="x-large" variant="tonal" prepend-icon="mdi-arrow-left" @click="openId = null">{{ t.common.back }}</v-btn>
      <div class="text-h4 font-weight-bold flex-grow-1" style="min-width: 0">{{ recipe?.name }}</div>
      <template v-if="recipe">
        <v-btn size="x-large" variant="tonal" prepend-icon="mdi-cart-plus" :disabled="!hasMissing" @click="missingToList">{{ t.recipes.missingToList }}</v-btn>
        <v-btn size="x-large" color="primary" variant="flat" prepend-icon="mdi-pot-steam-outline" @click="cookOpen = true">{{ t.recipes.cook }}</v-btn>
      </template>
    </div>
    <v-progress-linear v-if="!recipe" indeterminate color="primary" />
    <div v-else class="kiosk-recipe">
      <v-card variant="flat" border class="pa-4">
        <div class="text-h6 mb-2 d-flex align-center ga-2">
          {{ t.recipes.ingredients }}
          <v-chip v-if="fulfillment?.can_cook" color="success" variant="tonal" label prepend-icon="mdi-check">{{ t.recipes.cookable }}</v-chip>
          <v-chip v-else-if="fulfillment?.missing" color="warning" variant="tonal" label>{{ t.recipes.missingN(fulfillment.missing) }}</v-chip>
        </div>
        <div v-for="i in recipe.ingredients" :key="i.id" class="d-flex align-start ga-3 py-2">
          <v-icon :icon="statusIcon[statusById.get(i.id)?.status ?? 'unlinked']" :color="statusColor[statusById.get(i.id)?.status ?? 'unlinked']" size="26" class="mt-1" />
          <div>
            <div class="text-h6 font-weight-regular" :class="{ 'text-medium-emphasis': i.optional }">{{ i.text }}</div>
            <div v-if="statusById.get(i.id)?.in_stock != null" class="text-body-2 text-medium-emphasis">
              {{ t.recipes.inStock(formatAmount(statusById.get(i.id)!.in_stock!, statusById.get(i.id)!.unit)) }}
            </div>
          </div>
        </div>
      </v-card>
      <v-card variant="flat" border class="pa-4">
        <div class="text-h6 mb-2">{{ t.recipes.steps }}</div>
        <div v-if="!steps.length" class="text-h6 text-medium-emphasis font-weight-regular">{{ t.recipes.noSteps }}</div>
        <ol v-else class="kiosk-recipe__steps">
          <li v-for="(s, n) in steps" :key="n" class="d-flex ga-4 mb-5">
            <v-avatar color="primary" variant="tonal" size="44" class="text-h6 font-weight-bold flex-shrink-0">{{ n + 1 }}</v-avatar>
            <div class="kiosk-recipe__step">{{ s }}</div>
          </li>
        </ol>
      </v-card>
    </div>

    <v-dialog v-model="cookOpen" max-width="560">
      <v-card v-if="recipe" :title="t.recipes.cookTitle(recipe.name)">
        <v-card-text class="text-body-1">
          <template v-if="(fulfillment?.ingredients ?? []).some((i) => i.product_id && i.needed)">
            <div class="mb-2">{{ t.recipes.cookLeaves }}</div>
            <div v-for="i in (fulfillment?.ingredients ?? []).filter((i) => i.product_id && i.needed)" :key="i.ingredient_id">
              {{ i.product_name }} · {{ formatAmount(i.needed!, i.unit) }}
            </div>
          </template>
          <template v-else>{{ t.recipes.cookNothing }}</template>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn size="large" @click="cookOpen = false">{{ t.common.cancel }}</v-btn>
          <v-btn size="large" color="primary" variant="flat" :loading="busy" @click="cook">{{ t.recipes.cook }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>

  <!-- The list -->
  <div v-else>
    <KioskInput v-model="filter" :placeholder="t.recipes.searchPlaceholder" class="mb-4" @submit="submit" />
    <div v-if="!list.length" class="text-h6 text-medium-emphasis py-6 text-center">{{ suggestions.length ? t.recipes.noMatch : t.recipes.empty }}</div>
    <div class="kiosk-recipes">
      <v-card v-for="s in list" :key="s.recipe.id" variant="flat" border class="kiosk-recipes__card" @click="openId = s.recipe.id">
        <v-img v-if="s.recipe.photo_id" :src="fileUrl(s.recipe.photo_id, true)" height="130" cover />
        <div v-else class="kiosk-recipes__nophoto d-flex align-center justify-center"><v-icon icon="mdi-chef-hat" size="48" class="opacity-40" /></div>
        <v-card-text>
          <div class="text-h6 font-weight-bold kiosk-recipes__name">{{ s.recipe.name }}</div>
          <div class="d-flex flex-wrap ga-1 mt-2">
            <v-chip v-if="planned.has(s.recipe.id)" color="primary" variant="flat" label prepend-icon="mdi-calendar-today">{{ t.mealplan.today }}</v-chip>
            <v-chip v-if="s.fulfillment.can_cook" color="success" variant="tonal" label prepend-icon="mdi-check">{{ t.recipes.cookable }}</v-chip>
            <v-chip v-else-if="s.fulfillment.missing" color="warning" variant="tonal" label>{{ t.recipes.missingN(s.fulfillment.missing) }}</v-chip>
            <v-chip v-if="s.recipe.minutes" variant="outlined" label prepend-icon="mdi-timer-outline">{{ t.recipes.minutes(s.recipe.minutes) }}</v-chip>
          </div>
        </v-card-text>
      </v-card>
    </div>
  </div>
</template>

<style scoped>
.kiosk-recipe {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 3fr);
  gap: 20px;
  align-items: start;
}
@media (max-width: 900px) {
  .kiosk-recipe {
    grid-template-columns: minmax(0, 1fr);
  }
}
.kiosk-recipe__steps {
  list-style: none;
  padding: 0;
}
.kiosk-recipe__step {
  font-size: 1.4rem;
  line-height: 1.5;
  padding-top: 4px;
}
.kiosk-recipes {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px;
}
.kiosk-recipes__nophoto {
  height: 130px;
  background: rgb(var(--v-theme-surface-container));
}
.kiosk-recipes__name {
  line-height: 1.25;
}
</style>
