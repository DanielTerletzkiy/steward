<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { api } from '@/api'
import { LOCALE, t } from '@/i18n'
import { attempt, notify } from '@/composables/notify'
import { todayIso } from '@/composables/format'
import { SLOTS } from '@/composables/recipes'
import type { MealPlanEntry, MealSlot, Recipe, RecipeSuggestion } from '@/types'

// Add a meal (recipe or note) to the plan, or edit/move an existing one.
const open = defineModel<boolean>({ default: false })
const props = defineProps<{ entry?: MealPlanEntry | null; day?: string | null; mealSlot?: MealSlot | null; recipeId?: number | null }>()
const emit = defineEmits<{ saved: [MealPlanEntry] }>()
const { xs } = useDisplay()

const recipes = shallowRef<Recipe[]>([])
const fulfil = shallowRef(new Map<number, RecipeSuggestion['fulfillment']>())
const form = ref({ kind: 'recipe' as 'recipe' | 'note', recipe_id: null as number | null, note: '', day: todayIso(), slot: 'dinner' as MealSlot, servings: '' as string | number })
const busy = ref(false)

watch(open, async (v) => {
  if (!v) return
  const e = props.entry
  form.value = e
    ? { kind: e.recipe_id != null ? 'recipe' : 'note', recipe_id: e.recipe_id, note: e.note ?? '', day: e.day, slot: e.slot, servings: e.servings ?? '' }
    : { kind: 'recipe', recipe_id: props.recipeId ?? null, note: '', day: props.day ?? todayIso(), slot: props.mealSlot ?? 'dinner', servings: '' }
  const [list, suggestions] = await Promise.all([attempt(() => api.recipes()), attempt(() => api.recipeSuggestions(200))])
  recipes.value = (list ?? []).sort((a, b) => a.name.localeCompare(b.name, LOCALE))
  fulfil.value = new Map((suggestions ?? []).map((s) => [s.recipe.id, s.fulfillment]))
})

const recipeItems = computed(() => recipes.value.map((r) => ({ value: r.id, title: r.name, f: fulfil.value.get(r.id) })))
const slotItems = SLOTS.map((s) => ({ value: s, title: t.mealplan.slots[s] }))
const valid = computed(() => (form.value.kind === 'recipe' ? form.value.recipe_id != null : !!form.value.note.trim()) && !!form.value.day)

async function save() {
  if (!valid.value) return
  const f = form.value
  const servings = f.servings === '' || f.servings == null ? null : Math.max(1, Math.round(Number(f.servings)))
  const body = {
    day: f.day,
    slot: f.slot,
    recipe_id: f.kind === 'recipe' ? f.recipe_id : null,
    note: f.kind === 'note' ? f.note.trim() : null,
    servings: f.kind === 'recipe' && Number.isFinite(servings) ? servings : null,
  }
  busy.value = true
  const res = await attempt(() => (props.entry ? api.updateMeal(props.entry.id, body) : api.addMeal(body)))
  busy.value = false
  if (res) {
    notify(t.mealplan.saved)
    emit('saved', res)
    open.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" :fullscreen="xs" max-width="520" scrollable>
    <v-card :rounded="xs ? 0 : 'xl'">
      <v-toolbar color="transparent" density="comfortable">
        <v-btn icon="mdi-close" :title="t.common.close" @click="open = false" />
        <v-toolbar-title class="font-weight-medium">{{ entry ? t.mealplan.editMeal : t.mealplan.addMeal }}</v-toolbar-title>
      </v-toolbar>
      <v-divider />
      <v-card-text class="pt-4">
        <v-btn-toggle v-model="form.kind" mandatory color="primary" variant="outlined" divided density="comfortable" rounded="pill" class="mb-4">
          <v-btn value="recipe" prepend-icon="mdi-book-open-variant-outline">{{ t.mealplan.recipe }}</v-btn>
          <v-btn value="note" prepend-icon="mdi-note-text-outline">{{ t.mealplan.note }}</v-btn>
        </v-btn-toggle>
        <v-autocomplete
          v-if="form.kind === 'recipe'"
          v-model="form.recipe_id"
          :items="recipeItems"
          :label="t.mealplan.recipe"
          prepend-inner-icon="mdi-magnify"
          auto-select-first
        >
          <template #item="{ props: itemProps, item }">
            <v-list-item v-bind="itemProps">
              <template #append>
                <v-chip v-if="item.raw.f?.can_cook" size="x-small" color="success" variant="tonal" label>{{ t.mealplan.canCook }}</v-chip>
                <v-chip v-else-if="item.raw.f?.missing" size="x-small" color="warning" variant="tonal" label>{{ t.mealplan.missingN(item.raw.f.missing) }}</v-chip>
              </template>
            </v-list-item>
          </template>
        </v-autocomplete>
        <v-text-field v-else v-model="form.note" :label="t.mealplan.note" :placeholder="t.mealplan.notePlaceholder" persistent-placeholder />
        <v-row dense>
          <v-col cols="12" sm="6"><v-text-field v-model="form.day" type="date" :label="t.mealplan.day" /></v-col>
          <v-col cols="12" sm="6"><v-select v-model="form.slot" :items="slotItems" :label="t.mealplan.slot" /></v-col>
          <v-col v-if="form.kind === 'recipe'" cols="12">
            <v-text-field v-model="form.servings" type="number" min="1" :label="t.mealplan.servings" :hint="t.mealplan.servingsHint" persistent-hint />
          </v-col>
        </v-row>
      </v-card-text>
      <v-divider />
      <v-card-actions class="px-4">
        <v-spacer />
        <v-btn @click="open = false">{{ t.common.cancel }}</v-btn>
        <v-btn color="primary" variant="flat" :loading="busy" :disabled="!valid" @click="save">{{ entry ? t.common.save : t.mealplan.add }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
