<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { useCatalog } from '@/composables/catalog'
import { attempt, notify } from '@/composables/notify'
import { addDays, formatAmount, formatDate, todayIso } from '@/composables/format'
import { modeIcon, runScanAction, SCAN_MODES } from '@/composables/scanActions'
import type { Product, ScanLookup, ScanMode, StockItem } from '@/types'

const props = defineProps<{ result: ScanLookup; mode: ScanMode; stock: Map<number, StockItem> }>()
const emit = defineEmits<{ done: []; close: [] }>()
const { state, productsById, categories, units } = useCatalog()

const product = computed(() => (props.result.product_id != null ? productsById.value.get(props.result.product_id) ?? null : null))
const stockItem = computed(() => (product.value ? props.stock.get(product.value.id) ?? null : null))

const amount = ref<number | string>(1)
const dueDate = ref<string | null>(null)
const tab = ref<'new' | 'link'>('new')
const linkId = ref<number | null>(null)
const draft = ref({ name: '', brand: '', category: null as string | null, location_id: null as number | null, unit: 'Stk', due_days: null as number | null | string })
const busy = ref(false)

function defaultDue(p: Product | null): string | null {
  if (props.result.due_date) return props.result.due_date
  if (p?.due_days != null) return addDays(todayIso(), p.due_days)
  return null
}

watch(
  () => props.result,
  (r) => {
    amount.value = r.pack_amount ?? 1
    dueDate.value = defaultDue(product.value)
    const s = r.suggestion
    tab.value = r.similar_product_id && !s ? 'link' : 'new'
    linkId.value = r.similar_product_id ?? null
    draft.value = { name: s?.name ?? '', brand: s?.brand ?? '', category: s?.category ?? null, location_id: s?.location_id ?? null, unit: 'Stk', due_days: null }
  },
  { immediate: true },
)

const num = () => {
  const n = Number(String(amount.value).replace(',', '.'))
  return Number.isFinite(n) && n > 0 ? n : 1
}

async function act(p: Product, mode: ScanMode = props.mode) {
  busy.value = true
  const ok = await runScanAction(p, mode, num(), { dueDate: mode === 'purchase' ? dueDate.value : null, code: props.result.code })
  busy.value = false
  if (ok) emit('done')
}

async function createAndRun() {
  const d = draft.value
  if (!d.name.trim()) return
  busy.value = true
  const dueDays = d.due_days === '' || d.due_days == null ? null : Number(d.due_days)
  const created = await attempt(() =>
    api.createProduct({
      name: d.name.trim(),
      brand: d.brand.trim() || null,
      category: d.category || null,
      location_id: d.location_id,
      unit: d.unit || 'Stk',
      due_days: dueDays != null && Number.isFinite(dueDays) ? dueDays : null,
      image_url: props.result.suggestion?.image_url ?? null,
      barcodes: [props.result.code],
    }),
  )
  busy.value = false
  if (!created) return
  notify(t.scan.created)
  if (dueDate.value == null && created.due_days != null) dueDate.value = addDays(todayIso(), created.due_days)
  if (props.mode === 'lookup') emit('done')
  else await act(created)
}

async function linkAndRun() {
  if (linkId.value == null) return
  busy.value = true
  const linked = await attempt(() => api.addBarcode(linkId.value!, props.result.code, 1))
  busy.value = false
  if (!linked) return
  notify(t.scan.linked)
  if (props.mode === 'lookup') emit('done')
  else await act(linked)
}

const actionLabel = computed(() => t.scan.actions[props.mode])
const otherModes = computed(() => SCAN_MODES.filter((m) => m !== 'lookup'))
</script>

<template>
  <v-card variant="flat" border>
    <!-- Known product -->
    <template v-if="product">
      <v-card-item>
        <template #prepend>
          <v-avatar color="primary" variant="tonal" rounded="lg" size="48">
            <v-img v-if="product.image_url" :src="product.image_url" cover />
            <span v-else class="text-h6 font-weight-bold">{{ product.name.charAt(0).toUpperCase() }}</span>
          </v-avatar>
        </template>
        <v-card-title class="text-subtitle-1 font-weight-medium" style="white-space: normal">{{ product.name }}</v-card-title>
        <v-card-subtitle>
          {{ [product.brand, product.category].filter(Boolean).join(' · ') || t.scan.known }}
        </v-card-subtitle>
        <template #append><v-btn icon="mdi-close" variant="text" size="small" :title="t.common.close" @click="emit('close')" /></template>
      </v-card-item>
      <v-card-text class="pt-0">
        <div class="d-flex flex-wrap ga-1 mb-3">
          <v-chip :color="stockItem && stockItem.amount > 0 ? 'primary' : undefined" variant="tonal" label prepend-icon="mdi-fridge-outline">
            {{ stockItem && stockItem.amount > 0 ? t.scan.inStock(formatAmount(stockItem.amount, product.unit)) : t.scan.notInStock }}
          </v-chip>
          <v-chip variant="outlined" label prepend-icon="mdi-barcode">{{ result.code }}</v-chip>
          <v-chip v-if="result.lot" variant="outlined" label>{{ t.scan.lot }} {{ result.lot }}</v-chip>
        </div>
        <v-row v-if="mode !== 'lookup'" dense>
          <v-col :cols="mode === 'purchase' ? 5 : 12">
            <v-text-field v-model="amount" :label="t.scan.amount" type="number" min="0" step="any" :suffix="product.unit" hide-details="auto" />
          </v-col>
          <v-col v-if="mode === 'purchase'" cols="7">
            <v-text-field
              v-model="dueDate"
              type="date"
              :label="t.scan.dueDate"
              clearable
              :hint="result.due_date ? t.scan.dueFromCode : undefined"
              persistent-hint
            />
          </v-col>
        </v-row>
      </v-card-text>
      <v-card-actions class="px-4 pb-4 pt-0 flex-wrap ga-2">
        <template v-if="mode !== 'lookup'">
          <v-btn color="primary" variant="flat" size="large" block :prepend-icon="modeIcon[mode]" :loading="busy" @click="act(product)">{{ actionLabel }}</v-btn>
        </template>
        <template v-else>
          <v-btn v-for="m in otherModes" :key="m" variant="tonal" size="small" :prepend-icon="modeIcon[m]" :disabled="busy" @click="act(product, m)">{{ t.scan.modes[m] }}</v-btn>
        </template>
      </v-card-actions>
    </template>

    <!-- Unknown code -->
    <template v-else>
      <v-card-item>
        <template #prepend>
          <v-avatar :color="result.suggestion ? 'secondary' : 'warning'" variant="tonal" rounded="lg" size="48">
            <v-img v-if="result.suggestion?.image_url" :src="result.suggestion.image_url" cover />
            <v-icon v-else :icon="result.suggestion ? 'mdi-earth' : 'mdi-help-rhombus-outline'" />
          </v-avatar>
        </template>
        <v-card-title class="text-subtitle-1 font-weight-medium">{{ t.scan.unknown }}</v-card-title>
        <v-card-subtitle class="text-wrap">{{ result.suggestion ? t.scan.fromOff : t.scan.notFound }}</v-card-subtitle>
        <template #append><v-btn icon="mdi-close" variant="text" size="small" :title="t.common.close" @click="emit('close')" /></template>
      </v-card-item>
      <div class="px-4 pb-1 d-flex flex-wrap ga-1">
        <v-chip variant="outlined" label prepend-icon="mdi-barcode">{{ result.code }}</v-chip>
        <v-chip v-if="result.due_date" variant="tonal" color="info" label prepend-icon="mdi-calendar">{{ formatDate(result.due_date) }}</v-chip>
      </div>
      <v-tabs v-model="tab" color="primary" density="compact" grow class="mt-2">
        <v-tab value="new" prepend-icon="mdi-plus">{{ t.scan.createProduct }}</v-tab>
        <v-tab value="link" prepend-icon="mdi-link-variant">{{ t.scan.linkExisting }}</v-tab>
      </v-tabs>
      <v-divider />
      <v-card-text>
        <v-window v-model="tab" :touch="false">
          <v-window-item value="new">
            <v-text-field v-model="draft.name" :label="t.common.name" />
            <v-row dense>
              <v-col cols="6"><v-text-field v-model="draft.brand" :label="t.common.brand" /></v-col>
              <v-col cols="6"><v-combobox v-model="draft.category" :items="categories" :label="t.common.category" /></v-col>
              <v-col cols="6"><v-select v-model="draft.location_id" :items="state.locations" item-title="name" item-value="id" :label="t.common.location" clearable /></v-col>
              <v-col cols="6"><v-combobox v-model="draft.unit" :items="units" :label="t.common.unit" /></v-col>
              <v-col cols="6"><v-text-field v-model="draft.due_days" :label="t.stock.dueDays" type="number" min="0" /></v-col>
              <v-col v-if="mode !== 'lookup'" cols="6"><v-text-field v-model="amount" :label="t.scan.amount" type="number" min="0" step="any" /></v-col>
              <v-col v-if="mode === 'purchase'" cols="12"><v-text-field v-model="dueDate" type="date" :label="t.scan.dueDate" clearable /></v-col>
            </v-row>
            <v-btn color="primary" variant="flat" block size="large" :disabled="!draft.name.trim()" :loading="busy" prepend-icon="mdi-content-save-outline" @click="createAndRun">
              {{ mode === 'lookup' ? t.scan.saveOnly : t.scan.saveAndRun(actionLabel) }}
            </v-btn>
          </v-window-item>
          <v-window-item value="link">
            <v-alert v-if="result.similar_product_id" type="info" variant="tonal" density="compact" icon="mdi-lightbulb-outline" class="mb-3" :text="t.scan.similar" />
            <v-autocomplete
              v-model="linkId"
              :items="state.products"
              item-title="name"
              item-value="id"
              :label="t.receipts.pickProduct"
              prepend-inner-icon="mdi-magnify"
              auto-select-first
            />
            <v-row v-if="mode !== 'lookup'" dense>
              <v-col cols="6"><v-text-field v-model="amount" :label="t.scan.amount" type="number" min="0" step="any" /></v-col>
              <v-col v-if="mode === 'purchase'" cols="6"><v-text-field v-model="dueDate" type="date" :label="t.scan.dueDate" clearable /></v-col>
            </v-row>
            <v-btn color="primary" variant="flat" block size="large" :disabled="linkId == null" :loading="busy" prepend-icon="mdi-link-variant" @click="linkAndRun">
              {{ mode === 'lookup' ? t.scan.link : `${t.scan.link} · ${actionLabel}` }}
            </v-btn>
          </v-window-item>
        </v-window>
      </v-card-text>
    </template>
  </v-card>
</template>
