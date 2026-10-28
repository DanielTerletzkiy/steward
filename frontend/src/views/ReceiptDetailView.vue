<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { api } from '@/api'
import { t } from '@/i18n'
import { onTopics } from '@/composables/live'
import { useCatalog } from '@/composables/catalog'
import { attempt, notify } from '@/composables/notify'
import { formatDateTime, formatEuro, formatNumber } from '@/composables/format'
import LineMatchDialog from '@/components/LineMatchDialog.vue'
import type { Receipt, ReceiptLine } from '@/types'

const props = defineProps<{ id: number }>()
const { smAndUp } = useDisplay()
const { productsById } = useCatalog()

const receipt = ref<Receipt | null>(null)
const error = ref<string | null>(null)
async function load() {
  try {
    receipt.value = await api.receipt(props.id)
    error.value = null
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}
watch(() => props.id, load, { immediate: true })
onTopics(['receipts', 'catalog'], load)

const lineSum = computed(() => Math.round((receipt.value?.lines.reduce((s, l) => s + l.total, 0) ?? 0) * 100) / 100)
const diff = computed(() => (receipt.value ? Math.round((receipt.value.total - lineSum.value) * 100) / 100 : 0))
const unmatchedItems = computed(() => receipt.value?.lines.filter((l) => l.kind === 'item' && l.product_id == null).length ?? 0)

const kindIcon: Record<string, string> = { item: 'mdi-basket-outline', deposit: 'mdi-bottle-soda-classic-outline', deposit_return: 'mdi-recycle', bag: 'mdi-shopping-outline' }
const methodColor: Record<string, string> = { alias: 'success', manual: 'primary', fuzzy: 'warning' }

function needsReview(l: ReceiptLine) {
  return l.kind === 'item' && (l.product_id == null || l.method === 'fuzzy' || !l.confirmed)
}

const matchLine = ref<ReceiptLine | null>(null)
const matchOpen = ref(false)
function pick(l: ReceiptLine) {
  matchLine.value = l
  matchOpen.value = true
}
async function confirmLine(l: ReceiptLine) {
  if (l.product_id == null || !receipt.value) return
  const res = await attempt(() => api.matchLine(receipt.value!.id, l.id, { product_id: l.product_id! }))
  if (res) notify(t.receipts.lineMatched)
}

const stocking = ref(false)
async function toStock() {
  if (!receipt.value) return
  stocking.value = true
  const res = await attempt(() => api.stockReceipt(receipt.value!.id))
  stocking.value = false
  if (res) notify(t.receipts.stockedMsg(res.stocked))
}
</script>

<template>
  <div class="page" style="max-width: 900px">
    <v-btn variant="text" prepend-icon="mdi-arrow-left" to="/receipts" class="mb-2 ml-n3">{{ t.receipts.title }}</v-btn>
    <v-alert v-if="error" type="error" variant="tonal" :text="error" />
    <v-skeleton-loader v-else-if="!receipt" type="article, list-item@6" class="rounded-xl" />

    <template v-else>
      <v-card variant="flat" color="surface-container" class="mb-4">
        <v-card-text>
          <div class="d-flex flex-wrap align-start ga-4">
            <div class="min-w-0 flex-grow-1">
              <div class="text-h6">{{ receipt.store ?? receipt.chain }}</div>
              <div class="text-body-2 text-medium-emphasis">{{ formatDateTime(receipt.at) }}</div>
              <div class="d-flex flex-wrap ga-1 mt-2">
                <v-chip v-if="receipt.payment" variant="outlined" prepend-icon="mdi-credit-card-outline" label>{{ receipt.payment }}</v-chip>
                <v-chip v-if="receipt.loyalty" variant="outlined" prepend-icon="mdi-star-outline" label>{{ receipt.loyalty }}</v-chip>
                <v-chip v-if="receipt.stocked" color="primary" variant="tonal" prepend-icon="mdi-fridge-outline" label>{{ t.receipts.stocked }}</v-chip>
              </div>
            </div>
            <div :class="smAndUp ? 'text-right' : ''">
              <div class="text-caption text-medium-emphasis">{{ t.receipts.total }}</div>
              <div class="text-h4 font-weight-bold text-tabular">{{ formatEuro(receipt.total) }}</div>
              <div class="text-caption text-medium-emphasis text-tabular">{{ t.receipts.lineSum }}: {{ formatEuro(lineSum) }}</div>
              <div v-if="Math.abs(diff) >= 0.01" class="text-caption text-warning text-tabular">{{ t.receipts.diff }}: {{ formatEuro(diff) }}</div>
            </div>
          </div>
        </v-card-text>
        <v-card-actions v-if="!receipt.stocked" class="px-4 pb-4 flex-wrap">
          <v-btn color="primary" variant="flat" prepend-icon="mdi-fridge-variant-outline" :loading="stocking" @click="toStock">{{ t.receipts.toStock }}</v-btn>
          <span v-if="unmatchedItems" class="text-caption text-warning ml-2">{{ t.receipts.unmatchedHint(unmatchedItems) }}</span>
        </v-card-actions>
      </v-card>

      <div class="text-subtitle-1 font-weight-medium mb-2">{{ t.receipts.lines }} ({{ receipt.lines.length }})</div>
      <v-card variant="flat" border>
        <v-list bg-color="transparent" lines="three">
          <template v-for="(l, idx) in [...receipt.lines].sort((a, b) => a.idx - b.idx)" :key="l.id">
            <v-divider v-if="idx > 0" />
            <v-list-item class="py-3" :class="l.kind === 'item' && l.product_id == null ? 'bg-warning-lighten' : ''">
              <template #prepend>
                <v-avatar :color="l.kind !== 'item' ? 'grey' : l.product_id == null ? 'warning' : 'primary'" variant="tonal" size="40">
                  <v-icon :icon="kindIcon[l.kind] ?? 'mdi-help'" size="20" />
                </v-avatar>
              </template>
              <div class="d-flex align-start ga-2">
                <div class="min-w-0 flex-grow-1">
                  <div class="text-body-1 font-weight-medium" style="font-family: ui-monospace, Menlo, monospace; letter-spacing: 0.02em">{{ l.raw_text }}</div>
                  <div class="text-body-2 text-medium-emphasis text-tabular">
                    <template v-if="l.qty !== 1 || l.unit_price != null">{{ formatNumber(l.qty) }}{{ l.unit ? ` ${l.unit}` : '' }} × {{ formatEuro(l.unit_price ?? l.total / (l.qty || 1)) }}</template>
                    <template v-else>{{ t.receipts.kinds[l.kind] ?? l.kind }}</template>
                    <template v-if="l.tax"> · {{ l.tax }}</template>
                  </div>
                </div>
                <div class="text-body-1 font-weight-bold text-tabular text-no-wrap" :class="l.total < 0 ? 'text-success' : ''">{{ formatEuro(l.total) }}</div>
              </div>
              <div class="d-flex flex-wrap align-center ga-1 mt-2">
                <v-chip v-if="l.kind !== 'item'" variant="outlined" label>{{ t.receipts.kinds[l.kind] ?? l.kind }}</v-chip>
                <template v-else-if="l.product_id != null">
                  <v-chip color="primary" variant="tonal" prepend-icon="mdi-link-variant" label>{{ productsById.get(l.product_id)?.name ?? `#${l.product_id}` }}</v-chip>
                  <v-chip v-if="l.method" :color="methodColor[l.method] ?? 'grey'" variant="outlined" label>
                    {{ t.receipts.methods[l.method] ?? l.method }}<template v-if="l.method === 'fuzzy' || l.confidence < 1"> · {{ Math.round(l.confidence * 100) }} %</template>
                  </v-chip>
                </template>
                <v-chip v-else color="warning" variant="tonal" prepend-icon="mdi-link-variant-off" label>{{ t.receipts.unmatchedLine }}</v-chip>
                <v-spacer />
                <template v-if="l.kind === 'item'">
                  <v-btn v-if="l.product_id != null && needsReview(l)" size="small" variant="tonal" color="success" prepend-icon="mdi-check" @click="confirmLine(l)">{{ t.receipts.confirm }}</v-btn>
                  <v-btn
                    size="small"
                    :variant="l.product_id == null ? 'flat' : 'text'"
                    :color="l.product_id == null ? 'primary' : undefined"
                    :prepend-icon="l.product_id == null ? 'mdi-link-plus' : 'mdi-pencil'"
                    @click="pick(l)"
                  >{{ l.product_id == null ? t.receipts.choose : smAndUp ? t.receipts.change : '' }}</v-btn>
                </template>
              </div>
            </v-list-item>
          </template>
        </v-list>
      </v-card>
      <LineMatchDialog v-model="matchOpen" :receipt-id="receipt.id" :line="matchLine" @saved="load" />
    </template>
  </div>
</template>
