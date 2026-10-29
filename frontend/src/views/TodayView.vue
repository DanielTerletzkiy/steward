<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '@/api'
import { LOCALE, t } from '@/i18n'
import { useResource } from '@/composables/resource'
import { useCatalog } from '@/composables/catalog'
import { attempt, notify } from '@/composables/notify'
import { consume } from '@/composables/stockActions'
import {
  formatAmount, formatDate, formatDateTime, formatEuro, mdiIcon, parseDateTime, parseDay, relativeDue, relativeExpiry, todayIso,
} from '@/composables/format'
import { label, sourceIcon } from '@/composables/wardrobe'
import { completeMeal, SLOTS } from '@/composables/recipes'
import { kindIcon, liveSummary } from '@/composables/appliances'
import EmptyState from '@/components/EmptyState.vue'
import StatusChip from '@/components/StatusChip.vue'
import OutfitCollage from '@/components/OutfitCollage.vue'
import MealDoneDialog from '@/components/MealDoneDialog.vue'
import LaundryPromptBanner from '@/components/LaundryPromptBanner.vue'
import LaundryPanel from '@/components/LaundryPanel.vue'
import type { Chore, Equipment, Garment, MealPlanEntry, Summary } from '@/types'

const { data, loading, error, reload } = useResource<Summary | null>(
  () => api.summary(),
  ['stock', 'shopping', 'chores', 'tasks', 'receipts', 'people', 'catalog', 'wardrobe', 'equipment', 'mealplan', 'recipes', 'settings'],
  null,
)
const { data: garments } = useResource<Garment[]>(() => api.garments(), ['wardrobe'], [])
const { productsById, personName } = useCatalog()

type TodayMeal = Summary['meals_today'][number]
const todaysMeals = computed(() => [...(data.value?.meals_today ?? [])].sort((a, b) => SLOTS.indexOf(a.slot) - SLOTS.indexOf(b.slot)))
const mealName = (m: TodayMeal | MealPlanEntry) =>
  (m.recipe_id != null ? ('name' in m && m.name) || t.mealplan.deletedRecipe : m.note ?? '') as string
const mealLink = (m: TodayMeal) => (m.recipe_id != null && m.name ? `/recipes/${m.recipe_id}` : '/mealplan')
const asEntry = (m: TodayMeal): MealPlanEntry => ({ id: m.id, day: todayIso(), slot: m.slot, recipe_id: m.recipe_id, note: m.note, servings: m.servings, done: m.done })
const mealDoneName = ref('')
const mealDoneOpen = ref(false)
const mealDoneFor = ref<MealPlanEntry | null>(null)
async function mealDone(m: TodayMeal) {
  if (m.recipe_id == null) return void (await completeMeal(asEntry(m), false))
  mealDoneFor.value = asEntry(m)
  mealDoneName.value = mealName(m)
  mealDoneOpen.value = true
}

const garmentsById = computed(() => new Map(garments.value.map((g) => [g.id, g])))
const outfitsToday = computed(() =>
  Object.entries(data.value?.wardrobe.outfits_today ?? {})
    .map(([owner, outfit]) => ({ owner, name: owner ? personName(owner) ?? owner : t.today.household, outfit }))
    .sort((a, b) => a.name.localeCompare(b.name, LOCALE)),
)
const laundryPieces = computed(() => garments.value.filter((g) => g.state === 'laundry' || g.state === 'washing'))
const { data: equipmentList } = useResource<Equipment[]>(() => api.equipmentList(), ['equipment'], [])
const hasWasher = computed(() => equipmentList.value.some((e) => e.kind === 'washer' && (!!e.ha_device_id || e.ha_entities.length > 0)))

const greeting = computed(() => {
  const h = new Date().getHours()
  return h < 11 ? t.today.greetingMorning : h < 18 ? t.today.greetingDay : t.today.greetingEvening
})
const todayLabel = new Intl.DateTimeFormat(LOCALE, { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date())

const expiring = computed(() => {
  if (!data.value) return []
  return [
    ...data.value.stock.expired.map((i) => ({ ...i, status: 'expired' })),
    ...data.value.stock.due_soon.map((i) => ({ ...i, status: 'due_soon' })),
  ].sort((a, b) => (a.due ?? '').localeCompare(b.due ?? ''))
})
const dueChores = computed<Chore[]>(() => (data.value ? [...data.value.chores.overdue, ...data.value.chores.due_today] : []))

async function choreDone(c: Chore) {
  const res = await attempt(() => api.executeChore(c.id))
  if (res) notify(t.chores.doneMsg(c.name))
}
async function taskDone(task: { id: number; name: string }) {
  const res = await attempt(() => api.updateTask(task.id, { done: true }))
  if (res)
    notify(t.tasks.doneMsg(task.name), {
      action: { label: t.common.undo, run: async () => void (await attempt(() => api.updateTask(task.id, { done: false }))) },
    })
}
async function addMissing() {
  const lists = await attempt(() => api.shoppingLists())
  if (!lists?.length) return
  const res = await attempt(() => api.addMissing(lists[0].id))
  if (res) notify(t.shopping.added(res.added))
}
async function consumeOne(productId: number, spoiled = false) {
  const p = productsById.value.get(productId)
  if (p) await consume(p, 1, spoiled)
}
</script>

<template>
  <div class="page has-fab">
    <div class="mb-5">
      <div class="page-title">{{ greeting }}</div>
      <div class="text-body-2 text-medium-emphasis">{{ todayLabel }}</div>
    </div>

    <v-alert v-if="error && !data" type="error" variant="tonal" :title="t.app.loadError" :text="error" class="mb-4">
      <template #append><v-btn variant="text" @click="reload">{{ t.app.retry }}</v-btn></template>
    </v-alert>

    <v-row v-if="loading && !data">
      <v-col v-for="i in 6" :key="i" cols="12" md="6" lg="4"><v-skeleton-loader type="card" class="rounded-xl" /></v-col>
    </v-row>

    <v-row v-else-if="data">
      <v-col v-if="data.wardrobe.laundry_prompt" cols="12">
        <LaundryPromptBanner :prompt="data.wardrobe.laundry_prompt" :pieces="laundryPieces" @changed="reload" />
      </v-col>
      <!-- Spending / key numbers -->
      <v-col cols="12">
        <v-row dense>
          <v-col cols="6" md="3">
            <v-card color="primary" variant="flat" class="h-100">
              <v-card-text>
                <div class="text-caption opacity-80">{{ t.today.spending }}</div>
                <div class="text-h5 font-weight-bold text-tabular">{{ formatEuro(data.spending.month_total) }}</div>
                <div class="text-caption opacity-80">{{ t.today.trips(data.spending.month_trips) }}</div>
              </v-card-text>
            </v-card>
          </v-col>
          <v-col cols="6" md="3">
            <v-card variant="tonal" color="secondary" class="h-100" :to="data.spending.last_trip ? `/receipts/${data.spending.last_trip.receipt_id}` : undefined">
              <v-card-text>
                <div class="text-caption">{{ t.today.lastTrip }}</div>
                <template v-if="data.spending.last_trip">
                  <div class="text-h5 font-weight-bold text-tabular">{{ formatEuro(data.spending.last_trip.total) }}</div>
                  <div class="text-caption text-truncate">{{ formatDateTime(data.spending.last_trip.at) }} · {{ t.today.items(data.spending.last_trip.items) }}</div>
                </template>
                <div v-else class="text-body-2 mt-2">{{ t.today.noReceipts }}</div>
              </v-card-text>
            </v-card>
          </v-col>
          <v-col cols="6" md="3">
            <v-card variant="tonal" color="secondary" class="h-100">
              <v-card-text>
                <div class="text-caption d-flex align-center">
                  {{ t.today.deposit }}
                  <v-tooltip :text="`${t.today.depositHint}. ${t.today.bottlesHint}`" location="top" max-width="320">
                    <template #activator="{ props }"><v-icon v-bind="props" icon="mdi-information-outline" size="14" class="ml-1" /></template>
                  </v-tooltip>
                </div>
                <div class="text-h5 font-weight-bold text-tabular" :class="data.spending.deposit_balance < 0 ? 'text-warning' : ''">
                  {{ formatEuro(data.spending.deposit_balance) }}
                </div>
                <div class="text-caption">
                  <template v-if="!data.spending.deposit_bottles?.bought && !data.spending.deposit_bottles?.returned">{{ t.today.depositSub }}</template>
                  <template v-else-if="data.spending.deposit_bottles.open >= 0">{{ t.today.bottlesOpen(data.spending.deposit_bottles.open) }}</template>
                  <template v-else>{{ t.today.bottlesOver(-data.spending.deposit_bottles.open) }}</template>
                </div>
              </v-card-text>
            </v-card>
          </v-col>
          <v-col cols="6" md="3">
            <v-card variant="tonal" color="secondary" class="h-100" to="/stock">
              <v-card-text>
                <div class="text-caption">{{ t.today.stockValue }}</div>
                <div class="text-h5 font-weight-bold text-tabular">{{ formatEuro(data.stock.value) }}</div>
                <div class="text-caption">{{ t.today.productsInStock(data.stock.products_in_stock) }}</div>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>
      </v-col>

      <!-- Today's meals -->
      <v-col cols="12" md="6" lg="4">
        <v-card class="h-100" variant="flat" border>
          <v-card-item prepend-icon="mdi-silverware-fork-knife" :title="t.mealplan.todayMeals">
            <template #append><v-btn icon="mdi-chevron-right" variant="text" size="small" to="/mealplan" :title="t.nav.mealplan" /></template>
          </v-card-item>
          <EmptyState v-if="!todaysMeals.length" compact icon="mdi-calendar-blank-outline" :title="t.mealplan.noMealsToday">
            <v-btn color="primary" variant="tonal" prepend-icon="mdi-calendar-plus" to="/mealplan">{{ t.mealplan.planMeals }}</v-btn>
          </EmptyState>
          <v-list v-else density="comfortable" bg-color="transparent">
            <v-list-item
              v-for="m in todaysMeals"
              :key="m.id"
              :to="mealLink(m)"
              :prepend-icon="m.recipe_id != null ? t.mealplan.slotIcons[m.slot] : 'mdi-note-text-outline'"
            >
              <v-list-item-title :class="{ 'line-through text-medium-emphasis': m.done }">{{ mealName(m) }}</v-list-item-title>
              <v-list-item-subtitle>{{ t.mealplan.slots[m.slot] }}</v-list-item-subtitle>
              <template #append>
                <v-chip v-if="m.done" color="success" variant="tonal" size="small" prepend-icon="mdi-check" label>{{ t.mealplan.done }}</v-chip>
                <v-btn v-else color="primary" variant="tonal" size="small" prepend-icon="mdi-check" @click.stop.prevent="mealDone(m)">{{ t.common.done }}</v-btn>
              </template>
            </v-list-item>
          </v-list>
        </v-card>
      </v-col>

      <!-- Running now -->
      <v-col v-if="data.equipment.running.length" cols="12" md="6" lg="4">
        <v-card class="h-100" variant="flat" border>
          <v-card-item prepend-icon="mdi-play-circle-outline" :title="t.appliances.runningNow">
            <template #append><v-chip color="primary" variant="tonal">{{ data.equipment.running.length }}</v-chip></template>
          </v-card-item>
          <v-list density="comfortable" bg-color="transparent">
            <v-list-item v-for="r in data.equipment.running" :key="r.id" :to="`/equipment/${r.id}`" :title="r.name" append-icon="mdi-chevron-right">
              <template #prepend>
                <v-avatar color="primary" variant="tonal" size="36" class="running-avatar"><v-icon :icon="kindIcon[r.kind] ?? 'mdi-devices'" size="20" /></v-avatar>
              </template>
              <v-list-item-subtitle class="text-primary">{{ liveSummary(r.kind, { ...r, running: true }).text }}</v-list-item-subtitle>
            </v-list-item>
          </v-list>
        </v-card>
      </v-col>

      <!-- Chores -->
      <v-col cols="12" md="6" lg="4">
        <v-card class="h-100" variant="flat" border>
          <v-card-item prepend-icon="mdi-broom" :title="t.today.chores">
            <template #append><v-chip v-if="dueChores.length" color="warning" variant="tonal">{{ dueChores.length }}</v-chip></template>
          </v-card-item>
          <EmptyState v-if="!dueChores.length" compact icon="mdi-party-popper" :title="t.today.noChores" />
          <v-list v-else lines="two" density="comfortable" bg-color="transparent">
            <v-list-item v-for="c in dueChores" :key="c.id" :prepend-icon="mdiIcon(c.icon)">
              <v-list-item-title>{{ c.name }}</v-list-item-title>
              <v-list-item-subtitle>
                <span :class="c.status === 'overdue' ? 'text-error' : 'text-warning'">{{ c.next_due ? relativeDue(parseDateTime(c.next_due)) : '' }}</span>
                · {{ personName(c.next_assignee) ?? t.chores.everyone }}
              </v-list-item-subtitle>
              <template #append>
                <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-check" @click="choreDone(c)">{{ t.common.done }}</v-btn>
              </template>
            </v-list-item>
          </v-list>
        </v-card>
      </v-col>

      <!-- Expiring -->
      <v-col cols="12" md="6" lg="4">
        <v-card class="h-100" variant="flat" border>
          <v-card-item prepend-icon="mdi-clock-alert-outline" :title="t.today.expiring">
            <template #append><v-chip v-if="data.stock.expired.length" color="error" variant="tonal">{{ data.stock.expired.length }}</v-chip></template>
          </v-card-item>
          <EmptyState v-if="!expiring.length" compact icon="mdi-leaf" :title="t.today.nothingExpiring" />
          <v-list v-else density="comfortable" lines="two" bg-color="transparent">
            <v-list-item v-for="i in expiring" :key="i.product_id">
              <v-list-item-title>{{ i.name }}</v-list-item-title>
              <v-list-item-subtitle>{{ formatAmount(i.amount, i.unit) }} · {{ relativeExpiry(i.due) }}</v-list-item-subtitle>
              <template #append>
                <StatusChip :status="i.status" class="mr-1 d-none d-sm-flex" />
                <v-menu>
                  <template #activator="{ props }"><v-btn v-bind="props" icon="mdi-dots-vertical" variant="text" size="small" /></template>
                  <v-list density="compact">
                    <v-list-item prepend-icon="mdi-minus" :title="t.stock.consume" @click="consumeOne(i.product_id)" />
                    <v-list-item prepend-icon="mdi-delete-variant" :title="t.stock.spoil" @click="consumeOne(i.product_id, true)" />
                  </v-list>
                </v-menu>
              </template>
            </v-list-item>
          </v-list>
        </v-card>
      </v-col>

      <!-- Below min -->
      <v-col cols="12" md="6" lg="4">
        <v-card class="h-100" variant="flat" border>
          <v-card-item prepend-icon="mdi-arrow-down-bold-circle-outline" :title="t.today.belowMin">
            <template #append><v-chip v-if="data.stock.below_min.length" color="warning" variant="tonal">{{ data.stock.below_min.length }}</v-chip></template>
          </v-card-item>
          <EmptyState v-if="!data.stock.below_min.length" compact icon="mdi-check-all" :title="t.today.nothingBelowMin" />
          <template v-else>
            <v-list density="compact" bg-color="transparent">
              <v-list-item v-for="i in data.stock.below_min" :key="i.product_id" :title="i.name">
                <template #append><span class="text-body-2 text-medium-emphasis text-tabular">{{ formatAmount(i.amount, i.unit) }}</span></template>
              </v-list-item>
            </v-list>
            <v-card-actions>
              <v-btn color="primary" variant="tonal" prepend-icon="mdi-cart-plus" @click="addMissing">{{ t.today.addToList }}</v-btn>
            </v-card-actions>
          </template>
        </v-card>
      </v-col>

      <!-- Tasks -->
      <v-col cols="12" md="6" lg="4">
        <v-card class="h-100" variant="flat" border>
          <v-card-item prepend-icon="mdi-format-list-checks" :title="t.today.tasks" :subtitle="t.today.openTasks(data.tasks.open)" />
          <EmptyState v-if="!data.tasks.due.length" compact icon="mdi-check-circle-outline" :title="t.today.noTasks" />
          <v-list v-else density="comfortable" bg-color="transparent">
            <v-list-item v-for="task in data.tasks.due" :key="task.id" :title="task.name" :subtitle="relativeDue(parseDay(task.due))">
              <template #prepend>
                <v-checkbox-btn color="primary" @update:model-value="taskDone(task)" />
              </template>
            </v-list-item>
          </v-list>
          <v-card-actions><v-btn variant="text" to="/chores" append-icon="mdi-chevron-right">{{ t.today.allTasks }}</v-btn></v-card-actions>
        </v-card>
      </v-col>

      <!-- Today's outfit -->
      <v-col cols="12" md="6" lg="4">
        <v-card class="h-100" variant="flat" border>
          <v-card-item prepend-icon="mdi-hanger" :title="t.today.outfit">
            <template #append><v-btn icon="mdi-chevron-right" variant="text" size="small" to="/wardrobe" :title="t.nav.wardrobe" /></template>
          </v-card-item>
          <EmptyState v-if="!outfitsToday.length" compact icon="mdi-tshirt-crew-outline" :title="t.today.noOutfit">
            <v-btn color="primary" variant="tonal" prepend-icon="mdi-hanger" to="/wardrobe">{{ t.today.pickOutfit }}</v-btn>
          </EmptyState>
          <v-card-text v-else class="pt-0">
            <div v-for="o in outfitsToday" :key="o.owner" class="mb-3">
              <div class="d-flex align-center text-caption text-medium-emphasis mb-1">
                <span v-if="outfitsToday.length > 1 || o.owner" class="font-weight-medium text-high-emphasis mr-1">{{ o.name }} ·</span>
                <v-icon :icon="sourceIcon[o.outfit.source] ?? 'mdi-hanger'" size="14" class="mr-1" />{{ label.source(o.outfit.source) }}
                <v-spacer />
                <v-chip v-if="o.outfit.worn" color="success" variant="tonal" size="x-small" prepend-icon="mdi-check" label>{{ t.wardrobe.worn }}</v-chip>
              </div>
              <OutfitCollage :ids="o.outfit.garment_ids" :garments="garmentsById" row :max="5" :tile="64" />
              <div v-if="o.outfit.reason" class="text-body-2 text-medium-emphasis mt-1">{{ o.outfit.reason }}</div>
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Laundry -->
      <v-col cols="12" md="6" lg="4">
        <LaundryPanel :garments="garments" :has-washer="hasWasher" @open="() => $router.push('/wardrobe')" />
      </v-col>

      <!-- Warranty ending -->
      <v-col v-if="data.equipment.warranty_ending.length" cols="12" md="6" lg="4">
        <v-card class="h-100" variant="flat" border>
          <v-card-item prepend-icon="mdi-shield-alert-outline" :title="t.today.warrantyEnding">
            <template #append><v-chip color="warning" variant="tonal">{{ data.equipment.warranty_ending.length }}</v-chip></template>
          </v-card-item>
          <v-list density="comfortable" bg-color="transparent">
            <v-list-item v-for="e in data.equipment.warranty_ending" :key="e.id" :to="`/equipment/${e.id}`" :title="e.name" append-icon="mdi-chevron-right">
              <v-list-item-subtitle class="text-warning">{{ t.today.warrantyUntil(formatDate(e.warranty_until)) }}</v-list-item-subtitle>
            </v-list-item>
          </v-list>
        </v-card>
      </v-col>
    </v-row>
    <MealDoneDialog v-model="mealDoneOpen" :entry="mealDoneFor" :name="mealDoneName" />
    <v-btn class="scan-fab" color="primary" size="large" rounded="lg" elevation="4" prepend-icon="mdi-barcode-scan" to="/scan" height="56">{{ t.nav.scan }}</v-btn>
  </div>
</template>

<style scoped>
.running-avatar {
  animation: running-pulse 2s ease-in-out infinite;
}
@keyframes running-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(var(--v-theme-primary), 0.4);
  }
  50% {
    box-shadow: 0 0 0 6px rgba(var(--v-theme-primary), 0);
  }
}
</style>
