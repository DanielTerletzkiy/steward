<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import { api, fileUrl } from '@/api'
import { LOCALE, t } from '@/i18n'
import { useResource } from '@/composables/resource'
import { attempt } from '@/composables/notify'
import EmptyState from '@/components/EmptyState.vue'
import RecipeDialog from '@/components/RecipeDialog.vue'
import RecipeImportDialog from '@/components/RecipeImportDialog.vue'
import type { Recipe, RecipeSuggestion } from '@/types'

const { smAndUp } = useDisplay()
const router = useRouter()
const { data: recipes, loading, error, reload } = useResource<Recipe[]>(() => api.recipes(), ['recipes'], [])
const { data: suggestions } = useResource<RecipeSuggestion[]>(() => api.recipeSuggestions(8), ['recipes', 'stock', 'catalog'], [])

const search = ref('')
const tag = ref<string>('')
const favorites = ref(false)
const tags = computed(() => [...new Set(recipes.value.flatMap((r) => r.tags))].sort((a, b) => a.localeCompare(b, LOCALE)))
const visible = computed(() => {
  const q = search.value.trim().toLowerCase()
  return recipes.value
    .filter((r) => (!tag.value || r.tags.includes(tag.value)) && (!favorites.value || r.favorite))
    .filter((r) => !q || [r.name, r.description, ...r.tags, ...r.ingredients.map((i) => i.name)].join(' ').toLowerCase().includes(q))
    .sort((a, b) => Number(b.favorite) - Number(a.favorite) || a.name.localeCompare(b.name, LOCALE))
})
const fulfilById = computed(() => new Map(suggestions.value.map((s) => [s.recipe.id, s.fulfillment])))
const strip = computed(() => suggestions.value.filter((s) => s.fulfillment.can_cook || s.fulfillment.uses_expiring).slice(0, 8))

async function toggleFavorite(r: Recipe) {
  await attempt(() => api.updateRecipe(r.id, { favorite: !r.favorite }))
}

const dialog = ref(false)
const importOpen = ref(false)
const open = (r: Recipe) => router.push(`/recipes/${r.id}`)
</script>

<template>
  <div class="page">
    <div class="d-flex align-center mb-4">
      <div>
        <div class="page-title">{{ t.recipes.title }}</div>
        <div class="text-body-2 text-medium-emphasis">{{ t.recipes.count(recipes.length) }}</div>
      </div>
      <v-spacer />
      <v-btn variant="text" :icon="!smAndUp" class="mr-1" :title="t.recipes.import" @click="importOpen = true">
        <v-icon icon="mdi-web" />
        <span v-if="smAndUp" class="ml-2">{{ t.recipes.import }}</span>
      </v-btn>
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="dialog = true">{{ smAndUp ? t.recipes.newRecipe : t.common.create }}</v-btn>
    </div>

    <!-- What can I cook? -->
    <template v-if="strip.length">
      <div class="d-flex align-baseline mb-2">
        <div class="text-subtitle-1 font-weight-medium">{{ t.recipes.canCook }}</div>
        <div class="text-caption text-medium-emphasis ml-2 d-none d-sm-block">{{ t.recipes.canCookHint }}</div>
      </div>
      <div class="strip mb-5">
        <v-card v-for="s in strip" :key="s.recipe.id" variant="tonal" color="primary" class="strip__card" :to="`/recipes/${s.recipe.id}`">
          <v-img v-if="s.recipe.photo_id" :src="fileUrl(s.recipe.photo_id, true)" height="96" cover />
          <div v-else class="strip__placeholder d-flex align-center justify-center"><v-icon icon="mdi-silverware-fork-knife" size="32" class="opacity-60" /></div>
          <div class="pa-3">
            <div class="text-body-2 font-weight-bold text-high-emphasis text-truncate">{{ s.recipe.name }}</div>
            <div class="d-flex flex-wrap ga-1 mt-1">
              <v-chip v-if="s.fulfillment.can_cook" size="x-small" color="success" variant="flat" label prepend-icon="mdi-check">{{ t.recipes.cookable }}</v-chip>
              <v-chip v-else-if="s.fulfillment.missing" size="x-small" color="warning" variant="flat" label>{{ t.recipes.missingN(s.fulfillment.missing) }}</v-chip>
              <v-chip v-if="s.fulfillment.uses_expiring" size="x-small" color="warning" variant="tonal" label prepend-icon="mdi-clock-alert-outline">{{ s.fulfillment.uses_expiring }}</v-chip>
            </div>
          </div>
        </v-card>
      </div>
    </template>

    <v-row dense class="mb-1">
      <v-col cols="12" md="6">
        <v-text-field v-model="search" :placeholder="t.recipes.searchPlaceholder" prepend-inner-icon="mdi-magnify" clearable hide-details density="compact" variant="solo-filled" flat rounded="pill" />
      </v-col>
    </v-row>
    <div class="d-flex align-center ga-2 mb-2">
      <v-chip :color="favorites ? 'error' : undefined" :variant="favorites ? 'tonal' : 'outlined'" size="default" :prepend-icon="favorites ? 'mdi-heart' : 'mdi-heart-outline'" class="flex-shrink-0" @click="favorites = !favorites">
        {{ t.recipes.favorites }}
      </v-chip>
      <v-divider vertical class="my-2" />
      <v-chip-group v-model="tag" mandatory selected-class="text-primary" class="min-w-0">
        <v-chip value="" variant="outlined" size="default" filter>{{ t.recipes.allTags }}</v-chip>
        <v-chip v-for="tg in tags" :key="tg" :value="tg" variant="outlined" size="default" filter>{{ tg }}</v-chip>
      </v-chip-group>
    </div>

    <v-alert v-if="error" type="error" variant="tonal" :text="error" class="mb-4">
      <template #append><v-btn variant="text" @click="reload">{{ t.app.retry }}</v-btn></template>
    </v-alert>

    <v-row v-if="loading && !recipes.length" dense>
      <v-col v-for="i in 6" :key="i" cols="12" sm="6" md="4" lg="3"><v-skeleton-loader type="image, list-item-two-line" class="rounded-xl" /></v-col>
    </v-row>
    <EmptyState v-else-if="!recipes.length" icon="mdi-book-open-variant-outline" :title="t.recipes.empty" :text="t.recipes.emptyHint">
      <div class="d-flex ga-2">
        <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="dialog = true">{{ t.recipes.newRecipe }}</v-btn>
        <v-btn variant="tonal" prepend-icon="mdi-web" @click="importOpen = true">{{ t.recipes.import }}</v-btn>
      </div>
    </EmptyState>
    <EmptyState v-else-if="!visible.length" icon="mdi-magnify-close" :title="t.recipes.noMatch" />

    <v-row v-else dense>
      <v-col v-for="r in visible" :key="r.id" cols="12" sm="6" md="4" lg="3">
        <v-card variant="flat" border class="h-100 d-flex flex-column" @click="open(r)">
          <div class="position-relative">
            <v-img v-if="r.photo_id" :src="fileUrl(r.photo_id, true)" :aspect-ratio="16 / 10" cover />
            <v-sheet v-else color="surface-container" class="d-flex align-center justify-center" style="aspect-ratio: 16 / 10">
              <v-icon icon="mdi-silverware-fork-knife" size="40" class="opacity-40" />
            </v-sheet>
            <v-btn
              :icon="r.favorite ? 'mdi-heart' : 'mdi-heart-outline'"
              :color="r.favorite ? 'error' : undefined"
              size="small"
              variant="flat"
              class="fav-btn"
              :title="t.recipes.favorite"
              @click.stop="toggleFavorite(r)"
            />
          </div>
          <v-card-item class="pb-1">
            <v-card-title class="text-subtitle-1 font-weight-medium" style="white-space: normal; line-height: 1.3">{{ r.name }}</v-card-title>
            <v-card-subtitle class="mt-1">
              <template v-if="r.minutes"><v-icon icon="mdi-timer-outline" size="14" /> {{ t.recipes.minutes(r.minutes) }} · </template>{{ t.recipes.servingsN(r.servings) }}
            </v-card-subtitle>
          </v-card-item>
          <v-spacer />
          <div class="d-flex flex-wrap ga-1 px-4 pb-3">
            <v-chip v-if="fulfilById.get(r.id)?.can_cook" size="x-small" color="success" variant="tonal" label prepend-icon="mdi-check">{{ t.recipes.cookable }}</v-chip>
            <v-chip v-else-if="fulfilById.get(r.id)?.missing" size="x-small" color="warning" variant="tonal" label>{{ t.recipes.missingN(fulfilById.get(r.id)!.missing) }}</v-chip>
            <v-chip v-for="tg in r.tags" :key="tg" size="x-small" variant="outlined" label>{{ tg }}</v-chip>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <RecipeDialog v-model="dialog" :all-tags="tags" @saved="open" />
    <RecipeImportDialog v-model="importOpen" @imported="open" />
  </div>
</template>

<style scoped>
.strip {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 4px;
  scroll-snap-type: x mandatory;
  scrollbar-width: thin;
}
.strip__card {
  flex: 0 0 200px;
  scroll-snap-align: start;
}
.strip__placeholder {
  height: 96px;
  background: rgba(var(--v-theme-primary), 0.08);
}
.fav-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  background: rgba(var(--v-theme-surface), 0.85) !important;
}
</style>
