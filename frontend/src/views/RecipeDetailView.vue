<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import { api, ApiError, fileUrl } from '@/api'
import { t } from '@/i18n'
import { onTopics } from '@/composables/live'
import { attempt, notify } from '@/composables/notify'
import { formatAmount, formatDate } from '@/composables/format'
import { statusColor, statusIcon } from '@/composables/recipes'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import EmptyState from '@/components/EmptyState.vue'
import MealDialog from '@/components/MealDialog.vue'
import RecipeDialog from '@/components/RecipeDialog.vue'
import type { Fulfillment, Recipe } from '@/types'

const props = defineProps<{ id: number }>()
const router = useRouter()
const { smAndUp } = useDisplay()

const recipe = ref<Recipe | null>(null)
const fulfillment = ref<Fulfillment | null>(null)
const servings = ref<number | null>(null)
const error = ref<string | null>(null)
const notFound = ref(false)

async function load() {
  try {
    recipe.value = await api.recipe(props.id)
    servings.value ??= recipe.value.servings
    error.value = null
    notFound.value = false
    loadFulfillment()
  } catch (e) {
    notFound.value = e instanceof ApiError && e.status === 404
    error.value = e instanceof Error ? e.message : String(e)
  }
}
let seq = 0
async function loadFulfillment() {
  const mine = ++seq
  const res = await api.fulfillment(props.id, servings.value).catch(() => null)
  if (mine === seq) fulfillment.value = res
}
watch(
  () => props.id,
  () => {
    servings.value = null
    load()
  },
  { immediate: true },
)
watch(servings, (v, old) => old != null && v != null && loadFulfillment())
onTopics(['recipes'], load)
onTopics(['stock', 'catalog'], loadFulfillment)

const statusById = computed(() => new Map((fulfillment.value?.ingredients ?? []).map((i) => [i.ingredient_id, i])))
const groups = computed(() => {
  const out: { name: string | null; items: Recipe['ingredients'] }[] = []
  for (const i of recipe.value?.ingredients ?? []) {
    const last = out[out.length - 1]
    if (last && last.name === i.group) last.items.push(i)
    else out.push({ name: i.group, items: [i] })
  }
  return out
})
const steps = computed(() => (recipe.value?.instructions ?? '').split(/\r?\n/).map((s) => s.trim()).filter(Boolean))
const hasMissing = computed(() => (fulfillment.value?.ingredients ?? []).some((i) => i.status === 'missing' || i.status === 'partial'))
const leaving = computed(() => (fulfillment.value?.ingredients ?? []).filter((i) => i.product_id != null && (i.status === 'have' || i.status === 'partial') && i.needed))

function stepServings(d: number) {
  servings.value = Math.min(50, Math.max(1, (servings.value ?? 1) + d))
}

async function toggleFavorite() {
  if (!recipe.value) return
  const res = await attempt(() => api.updateRecipe(props.id, { favorite: !recipe.value!.favorite }))
  if (res) recipe.value = res
}

// --- cook
const cookOpen = ref(false)
const cooking = ref(false)
async function cook() {
  cooking.value = true
  const res = await attempt(() => api.cook(props.id, servings.value))
  cooking.value = false
  if (res) {
    cookOpen.value = false
    notify(`${t.recipes.cooked(recipe.value?.name ?? '')} · ${t.recipes.usedN(res.used.length)}`)
    load()
  }
}

const shopping = ref(false)
async function missingToList() {
  shopping.value = true
  const res = await attempt(() => api.recipeToShopping(props.id, servings.value))
  shopping.value = false
  if (res) notify(t.recipes.addedToList(res.added.length))
}

const planOpen = ref(false)
const editOpen = ref(false)
const confirmDelete = ref(false)
async function remove() {
  const ok = await attempt(async () => (await api.deleteRecipe(props.id), true))
  if (ok) {
    notify(t.recipes.deleted)
    router.push('/recipes')
  }
}
</script>

<template>
  <div class="page" style="max-width: 1100px">
    <v-btn variant="text" prepend-icon="mdi-arrow-left" to="/recipes" class="mb-2 ml-n3">{{ t.recipes.title }}</v-btn>

    <EmptyState v-if="notFound" icon="mdi-help-circle-outline" :title="t.recipes.notFound" />
    <v-alert v-else-if="error && !recipe" type="error" variant="tonal" :text="error" />
    <v-skeleton-loader v-else-if="!recipe" type="image, article, list-item@5" class="rounded-xl" />

    <template v-else>
      <v-card variant="flat" color="surface-container" class="mb-4 overflow-hidden">
        <div class="d-flex flex-column flex-md-row">
          <div class="hero-photo flex-shrink-0" :class="{ 'hero-photo--empty': !recipe.photo_id }">
            <v-img v-if="recipe.photo_id" :src="fileUrl(recipe.photo_id)" cover class="fill-height" />
            <div v-else class="fill-height d-flex align-center justify-center"><v-icon icon="mdi-silverware-fork-knife" size="64" class="opacity-30" /></div>
          </div>
          <div class="flex-grow-1 min-w-0 d-flex flex-column">
            <v-card-item>
              <v-card-title class="text-h5 font-weight-medium" style="white-space: normal; line-height: 1.25">{{ recipe.name }}</v-card-title>
              <template #append>
                <v-btn :icon="recipe.favorite ? 'mdi-heart' : 'mdi-heart-outline'" :color="recipe.favorite ? 'error' : undefined" variant="text" :title="t.recipes.favorite" @click="toggleFavorite" />
                <v-menu location="bottom end">
                  <template #activator="{ props: menuProps }"><v-btn v-bind="menuProps" icon="mdi-dots-vertical" variant="text" /></template>
                  <v-list density="compact">
                    <v-list-item prepend-icon="mdi-pencil-outline" :title="t.common.edit" @click="editOpen = true" />
                    <v-list-item v-if="recipe.source_url" prepend-icon="mdi-open-in-new" :title="t.recipes.source" :href="recipe.source_url" target="_blank" rel="noopener" />
                    <v-divider />
                    <v-list-item prepend-icon="mdi-delete-outline" base-color="error" :title="t.recipes.deleteRecipe" @click="confirmDelete = true" />
                  </v-list>
                </v-menu>
              </template>
            </v-card-item>
            <v-card-text class="pt-0">
              <div v-if="recipe.description" class="text-body-2 mb-3">{{ recipe.description }}</div>
              <div class="d-flex flex-wrap align-center ga-2 mb-3">
                <v-chip v-if="recipe.minutes" variant="outlined" label prepend-icon="mdi-timer-outline">{{ t.recipes.minutes(recipe.minutes) }}</v-chip>
                <v-chip v-for="tg in recipe.tags" :key="tg" variant="outlined" label>{{ tg }}</v-chip>
                <span v-if="recipe.cooked_count" class="text-caption text-medium-emphasis">
                  {{ t.recipes.cookedN(recipe.cooked_count) }}<template v-if="recipe.last_cooked"> · {{ t.recipes.lastCooked(formatDate(recipe.last_cooked)) }}</template>
                </span>
              </div>
              <div class="d-flex align-center">
                <span class="text-body-2 mr-3">{{ t.recipes.servings }}</span>
                <v-btn icon="mdi-minus" size="small" variant="tonal" :disabled="(servings ?? 1) <= 1" @click="stepServings(-1)" />
                <span class="text-h6 text-tabular mx-4" style="min-width: 2ch; text-align: center">{{ servings }}</span>
                <v-btn icon="mdi-plus" size="small" variant="tonal" :disabled="(servings ?? 1) >= 50" @click="stepServings(1)" />
              </div>
            </v-card-text>
            <v-spacer />
            <v-card-actions class="px-4 pb-4 flex-wrap ga-2">
              <v-btn color="primary" variant="flat" prepend-icon="mdi-pot-steam-outline" @click="cookOpen = true">{{ t.recipes.cook }}</v-btn>
              <v-btn variant="tonal" prepend-icon="mdi-cart-plus" :loading="shopping" :disabled="!hasMissing" @click="missingToList">{{ t.recipes.missingToList }}</v-btn>
              <v-btn variant="tonal" prepend-icon="mdi-calendar-plus" @click="planOpen = true">{{ t.recipes.addToPlan }}</v-btn>
            </v-card-actions>
          </div>
        </div>
      </v-card>

      <v-row>
        <v-col cols="12" md="5">
          <v-card variant="flat" border>
            <v-card-item prepend-icon="mdi-format-list-bulleted">
              <v-card-title class="text-subtitle-1 font-weight-medium">{{ t.recipes.ingredients }}</v-card-title>
              <template #append>
                <v-chip v-if="fulfillment?.can_cook" color="success" variant="tonal" label prepend-icon="mdi-check">{{ t.recipes.cookable }}</v-chip>
                <v-chip v-else-if="fulfillment?.missing" color="warning" variant="tonal" label>{{ t.recipes.missingN(fulfillment.missing) }}</v-chip>
              </template>
            </v-card-item>
            <v-alert v-if="fulfillment?.uses_expiring" type="warning" variant="tonal" density="compact" icon="mdi-clock-alert-outline" class="mx-4 mb-2" :text="t.recipes.usesExpiring(fulfillment.uses_expiring)" />
            <template v-for="(g, gi) in groups" :key="gi">
              <div v-if="g.name" class="text-overline text-medium-emphasis px-4 pt-2">{{ g.name }}</div>
              <v-list bg-color="transparent" density="compact" class="py-0">
                <v-list-item v-for="i in g.items" :key="i.id" class="py-2" :class="{ 'expiring-row': statusById.get(i.id)?.expiring }">
                  <template #prepend>
                    <v-icon
                      :icon="statusIcon[statusById.get(i.id)?.status ?? 'unlinked']"
                      :color="statusColor[statusById.get(i.id)?.status ?? 'unlinked']"
                      size="20"
                      :class="statusColor[statusById.get(i.id)?.status ?? 'unlinked'] ? '' : 'opacity-50'"
                    />
                  </template>
                  <v-list-item-title class="wrap" :class="{ 'text-medium-emphasis': i.optional }">{{ i.text }}</v-list-item-title>
                  <v-list-item-subtitle v-if="statusById.get(i.id)?.product_id" class="d-flex flex-wrap ga-1 mt-1">
                    <span>{{ statusById.get(i.id)!.product_name }}</span>
                    <span v-if="statusById.get(i.id)!.in_stock != null">· {{ t.recipes.inStock(formatAmount(statusById.get(i.id)!.in_stock!, statusById.get(i.id)!.unit)) }}</span>
                  </v-list-item-subtitle>
                  <template #append>
                    <div class="d-flex flex-column align-end ga-1">
                      <v-chip
                        v-if="statusById.get(i.id)"
                        size="x-small"
                        :color="statusColor[statusById.get(i.id)!.status]"
                        variant="tonal"
                        label
                      >{{ t.recipes.status[statusById.get(i.id)!.status] }}</v-chip>
                      <v-chip v-if="statusById.get(i.id)?.expiring" size="x-small" color="warning" variant="flat" label prepend-icon="mdi-clock-alert-outline">{{ t.recipes.expiring }}</v-chip>
                    </div>
                  </template>
                </v-list-item>
              </v-list>
            </template>
            <div class="pb-2" />
          </v-card>
        </v-col>
        <v-col cols="12" md="7">
          <v-card variant="flat" border>
            <v-card-item prepend-icon="mdi-chef-hat">
              <v-card-title class="text-subtitle-1 font-weight-medium">{{ t.recipes.steps }}</v-card-title>
            </v-card-item>
            <v-card-text v-if="!steps.length" class="text-medium-emphasis">{{ t.recipes.noSteps }}</v-card-text>
            <ol v-else class="steps px-4 pb-4">
              <li v-for="(s, i) in steps" :key="i" class="d-flex ga-3 mb-4">
                <v-avatar color="primary" variant="tonal" size="28" class="text-body-2 font-weight-bold flex-shrink-0">{{ i + 1 }}</v-avatar>
                <div class="text-body-1 pt-1" style="line-height: 1.55">{{ s }}</div>
              </li>
            </ol>
            <v-card-actions v-if="recipe.source_url" class="px-4 pt-0">
              <v-btn variant="text" size="small" prepend-icon="mdi-open-in-new" :href="recipe.source_url" target="_blank" rel="noopener" class="text-truncate" style="max-width: 100%">
                {{ t.recipes.source }}
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>

      <!-- Cook confirmation: what leaves stock -->
      <v-bottom-sheet v-if="!smAndUp" v-model="cookOpen">
        <v-card rounded="t-xl" :title="t.recipes.cookTitle(recipe.name)" prepend-icon="mdi-pot-steam-outline">
          <v-card-text>
            <div class="text-body-2 mb-2">{{ leaving.length ? t.recipes.cookLeaves : t.recipes.cookNothing }}</div>
            <v-list density="compact" bg-color="transparent" class="py-0">
              <v-list-item v-for="i in leaving" :key="i.ingredient_id" :title="i.product_name ?? i.name" prepend-icon="mdi-minus-circle-outline">
                <template #append><span class="text-body-2 text-tabular">{{ formatAmount(i.needed!, i.unit) }}</span></template>
              </v-list-item>
            </v-list>
          </v-card-text>
          <v-card-actions class="px-4 pb-4">
            <v-spacer />
            <v-btn @click="cookOpen = false">{{ t.common.cancel }}</v-btn>
            <v-btn color="primary" variant="flat" :loading="cooking" @click="cook">{{ t.recipes.cook }}</v-btn>
          </v-card-actions>
        </v-card>
      </v-bottom-sheet>
      <v-dialog v-else v-model="cookOpen" max-width="460">
        <v-card :title="t.recipes.cookTitle(recipe.name)" prepend-icon="mdi-pot-steam-outline">
          <v-card-text>
            <div class="text-body-2 mb-2">{{ leaving.length ? t.recipes.cookLeaves : t.recipes.cookNothing }}</div>
            <v-list density="compact" bg-color="transparent" class="py-0">
              <v-list-item v-for="i in leaving" :key="i.ingredient_id" :title="i.product_name ?? i.name" prepend-icon="mdi-minus-circle-outline">
                <template #append><span class="text-body-2 text-tabular">{{ formatAmount(i.needed!, i.unit) }}</span></template>
              </v-list-item>
            </v-list>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn @click="cookOpen = false">{{ t.common.cancel }}</v-btn>
            <v-btn color="primary" variant="flat" :loading="cooking" @click="cook">{{ t.recipes.cook }}</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <MealDialog v-model="planOpen" :recipe-id="recipe.id" />
      <RecipeDialog v-model="editOpen" :recipe="recipe" @saved="(r) => (recipe = r)" />
      <ConfirmDialog v-model="confirmDelete" :title="t.recipes.deleteRecipe" :text="t.recipes.confirmDelete(recipe.name)" @confirm="remove" />
    </template>
  </div>
</template>

<style scoped>
.hero-photo {
  width: 100%;
  aspect-ratio: 16 / 9;
  background: rgba(var(--v-theme-primary), 0.06);
}
.hero-photo--empty {
  aspect-ratio: auto;
  height: 96px;
}
@media (min-width: 960px) {
  .hero-photo {
    width: 340px;
    height: auto;
    aspect-ratio: auto;
    min-height: 240px;
  }
}
.steps {
  list-style: none;
}
.expiring-row {
  background: rgba(var(--v-theme-warning), 0.08);
}
</style>
