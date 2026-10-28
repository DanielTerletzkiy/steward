<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDisplay } from 'vuetify'
import { api, fileUrl } from '@/api'
import { LOCALE, t } from '@/i18n'
import { useResource } from '@/composables/resource'
import { attempt, notify } from '@/composables/notify'
import { addDays, parseDay, toIsoDay, todayIso } from '@/composables/format'
import { completeMeal, SLOTS } from '@/composables/recipes'
import MealDialog from '@/components/MealDialog.vue'
import MealDoneDialog from '@/components/MealDoneDialog.vue'
import type { MealPlanEntry, MealSlot, Recipe } from '@/types'

const { smAndUp } = useDisplay()

function mondayOf(iso: string) {
  const d = parseDay(iso)
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7))
  return toIsoDay(d)
}
const start = ref(mondayOf(todayIso()))
const end = computed(() => addDays(start.value, 6))
const isThisWeek = computed(() => start.value === mondayOf(todayIso()))

const { data: entries, loading, error, reload } = useResource<MealPlanEntry[]>(() => api.mealPlan(start.value, end.value), ['mealplan', 'recipes'], [])
const { data: recipes } = useResource<Recipe[]>(() => api.recipes(), ['recipes'], [])
const recipesById = computed(() => new Map(recipes.value.map((r) => [r.id, r])))

function go(weeks: number) {
  start.value = weeks === 0 ? mondayOf(todayIso()) : addDays(start.value, weeks * 7)
  reload()
}

const dayFmt = new Intl.DateTimeFormat(LOCALE, { weekday: 'long' })
const dateFmt = new Intl.DateTimeFormat(LOCALE, { day: 'numeric', month: 'short' })
const rangeLabel = computed(() => `${dateFmt.format(parseDay(start.value))} – ${dateFmt.format(parseDay(end.value))}`)

const days = computed(() =>
  Array.from({ length: 7 }, (_, i) => {
    const iso = addDays(start.value, i)
    const list = entries.value
      .filter((e) => e.day === iso)
      .sort((a, b) => SLOTS.indexOf(a.slot) - SLOTS.indexOf(b.slot) || a.id - b.id)
    return { iso, weekday: dayFmt.format(parseDay(iso)), date: dateFmt.format(parseDay(iso)), today: iso === todayIso(), past: iso < todayIso(), entries: list }
  }),
)

const nameOf = (e: MealPlanEntry) => (e.recipe_id != null ? recipesById.value.get(e.recipe_id)?.name ?? t.mealplan.deletedRecipe : e.note ?? '')

// --- dialogs
const mealOpen = ref(false)
const editing = ref<MealPlanEntry | null>(null)
const presetDay = ref<string | null>(null)
const presetSlot = ref<MealSlot | null>(null)
function add(day: string, slot: MealSlot | null = null) {
  editing.value = null
  presetDay.value = day
  presetSlot.value = slot ?? defaultSlot(day)
  mealOpen.value = true
}
function edit(e: MealPlanEntry) {
  editing.value = e
  mealOpen.value = true
}
function defaultSlot(day: string): MealSlot {
  const taken = new Set(entries.value.filter((e) => e.day === day).map((e) => e.slot))
  return (['dinner', 'lunch', 'breakfast', 'snack'] as MealSlot[]).find((s) => !taken.has(s)) ?? 'dinner'
}

const doneOpen = ref(false)
const doneFor = ref<MealPlanEntry | null>(null)
async function toggleDone(e: MealPlanEntry) {
  if (e.done) {
    await attempt(() => api.updateMeal(e.id, { done: false }))
    return
  }
  if (e.recipe_id == null) {
    await completeMeal(e, false)
    return
  }
  doneFor.value = e
  doneOpen.value = true
}
async function remove(e: MealPlanEntry) {
  const ok = await attempt(async () => (await api.deleteMeal(e.id), true))
  if (ok)
    notify(t.mealplan.removed, {
      action: {
        label: t.common.undo,
        run: async () => void (await attempt(() => api.addMeal({ day: e.day, slot: e.slot, recipe_id: e.recipe_id, note: e.note, servings: e.servings }))),
      },
    })
}

const shopping = ref(false)
async function toShopping() {
  shopping.value = true
  const from = start.value > todayIso() ? start.value : todayIso()
  const res = await attempt(() => api.mealPlanShopping(from, end.value))
  shopping.value = false
  if (res) notify(t.mealplan.added(res.added.length))
}
</script>

<template>
  <div class="page">
    <div class="d-flex flex-wrap align-center ga-2 mb-4">
      <div class="mr-2">
        <div class="page-title">{{ t.mealplan.title }}</div>
        <div class="text-body-2 text-medium-emphasis">{{ rangeLabel }}</div>
      </div>
      <v-spacer />
      <div class="d-flex align-center ga-1">
        <v-btn icon="mdi-chevron-left" variant="text" :title="t.mealplan.prev" @click="go(-1)" />
        <v-btn variant="tonal" size="small" :disabled="isThisWeek" @click="go(0)">{{ t.mealplan.today }}</v-btn>
        <v-btn icon="mdi-chevron-right" variant="text" :title="t.mealplan.next" @click="go(1)" />
      </div>
      <v-btn color="primary" variant="tonal" prepend-icon="mdi-cart-plus" :loading="shopping" :disabled="end < todayIso()" @click="toShopping">
        {{ smAndUp ? t.mealplan.shopping : t.mealplan.shoppingShort }}
      </v-btn>
    </div>

    <v-alert v-if="error" type="error" variant="tonal" :text="error" class="mb-4">
      <template #append><v-btn variant="text" @click="reload">{{ t.app.retry }}</v-btn></template>
    </v-alert>

    <v-row dense>
      <v-col v-for="d in days" :key="d.iso" cols="12" sm="6" lg="4" xl="3">
        <v-card variant="flat" :border="!d.today" :color="d.today ? 'surface-container' : undefined" class="h-100 d-flex flex-column" :class="{ 'opacity-70': d.past && !d.today, 'today-card': d.today }">
          <v-card-item class="pb-1">
            <v-card-title class="text-subtitle-1 font-weight-medium d-flex align-center">
              {{ d.weekday }}
              <v-chip v-if="d.today" size="x-small" color="primary" variant="flat" label class="ml-2">{{ t.mealplan.today }}</v-chip>
            </v-card-title>
            <v-card-subtitle>{{ d.date }}</v-card-subtitle>
            <template #append>
              <v-btn icon="mdi-plus" variant="tonal" size="small" color="primary" :title="t.mealplan.addMeal" @click="add(d.iso)" />
            </template>
          </v-card-item>
          <v-skeleton-loader v-if="loading && !entries.length" type="list-item" class="bg-transparent" />
          <div v-else-if="!d.entries.length" class="px-4 pb-4 text-body-2 text-medium-emphasis">{{ t.mealplan.nothing }}</div>
          <v-list v-else bg-color="transparent" density="comfortable" class="py-0">
            <v-list-item v-for="e in d.entries" :key="e.id" class="meal" :to="e.recipe_id != null && recipesById.has(e.recipe_id) ? `/recipes/${e.recipe_id}` : undefined">
              <template #prepend>
                <v-avatar v-if="e.recipe_id != null && recipesById.get(e.recipe_id)?.photo_id" size="40" rounded="lg" class="mr-1">
                  <v-img :src="fileUrl(recipesById.get(e.recipe_id)!.photo_id!, true)" cover />
                </v-avatar>
                <v-avatar v-else size="40" rounded="lg" :color="e.recipe_id != null ? 'primary' : 'secondary'" variant="tonal" class="mr-1">
                  <v-icon :icon="e.recipe_id != null ? t.mealplan.slotIcons[e.slot] : 'mdi-note-text-outline'" size="20" />
                </v-avatar>
              </template>
              <div class="text-caption text-medium-emphasis">{{ t.mealplan.slots[e.slot] }}<template v-if="e.servings"> · {{ t.recipes.servingsN(e.servings) }}</template></div>
              <v-list-item-title class="wrap" :class="{ 'line-through text-medium-emphasis': e.done, 'font-italic': e.recipe_id == null }">{{ nameOf(e) }}</v-list-item-title>
              <template #append>
                <div class="d-flex align-center" @click.stop.prevent>
                  <v-btn
                    :icon="e.done ? 'mdi-check-circle' : 'mdi-check-circle-outline'"
                    :color="e.done ? 'success' : undefined"
                    variant="text"
                    size="small"
                    :title="e.done ? t.mealplan.undoDone : t.mealplan.markDone"
                    @click="toggleDone(e)"
                  />
                  <v-menu location="bottom end">
                    <template #activator="{ props: menuProps }"><v-btn v-bind="menuProps" icon="mdi-dots-vertical" variant="text" size="small" /></template>
                    <v-list density="compact">
                      <v-list-item prepend-icon="mdi-calendar-arrow-right" :title="t.mealplan.move" @click="edit(e)" />
                      <v-list-item prepend-icon="mdi-delete-outline" base-color="error" :title="t.mealplan.remove" @click="remove(e)" />
                    </v-list>
                  </v-menu>
                </div>
              </template>
            </v-list-item>
          </v-list>
        </v-card>
      </v-col>
    </v-row>

    <MealDialog v-model="mealOpen" :entry="editing" :day="presetDay" :meal-slot="presetSlot" />
    <MealDoneDialog v-model="doneOpen" :entry="doneFor" :name="doneFor ? nameOf(doneFor) : ''" />
  </div>
</template>

<style scoped>
.today-card {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.meal :deep(.v-list-item__prepend) {
  align-self: center;
}
</style>
