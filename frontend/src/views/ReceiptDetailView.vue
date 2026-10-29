<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import { api } from '@/api'
import { t } from '@/i18n'
import { onTopics } from '@/composables/live'
import { useCatalog } from '@/composables/catalog'
import { attempt, notify } from '@/composables/notify'
import { formatDateTime, formatEuro, formatNumber } from '@/composables/format'
import LineMatchDialog from '@/components/LineMatchDialog.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import type { Receipt, ReceiptLine } from '@/types'

const props = defineProps<{ id: number }>()
const { smAndUp } = useDisplay()
const { productsById } = useCatalog()

const receipt = ref<Receipt | null>(null)
const error = ref<string | null>(null)
let deleted = false
async function load() {
  if (deleted) return
  try {
    receipt.value = await api.receipt(props.id)
    error.value = null
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}
watch(() => props.id, load, { immediate: true })
onTopics(['receipts', 'catalog'], load)

const router = useRouter()
const confirmDelete = ref(false)
async function remove() {
  const r = receipt.value
  if (!r) return
  deleted = true
  if (await attempt(async () => (await api.deleteReceipt(r.id), true))) {
    notify(t.receipts.deleted)
    router.replace('/receipts')
  } else deleted = false
}

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

// Pieces per pack: 6 bottles in a 6-pack go into stock as 6.
const piecesLine = ref<ReceiptLine | null>(null)
const piecesValue = ref<string | number>(1)
const piecesOpen = ref(false)
const savingPieces = ref(false)
function editPieces(l: ReceiptLine) {
  piecesLine.value = l
  piecesValue.value = l.pieces ?? 1
  piecesOpen.value = true
}
const piecesNumber = computed(() => Number(String(piecesValue.value).replace(',', '.')))
async function savePieces() {
  const l = piecesLine.value
  if (!l || !receipt.value || !(piecesNumber.value > 0)) return
  savingPieces.value = true
  const res = await attempt(() => api.setLinePieces(receipt.value!.id, l.id, piecesNumber.value))
  savingPieces.value = false
  if (!res) return
  piecesOpen.value = false
  notify(t.receipts.piecesSaved)
  load()
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
    <div class="d-flex align-center mb-2">
      <v-btn variant="text" prepend-icon="mdi-arrow-left" to="/receipts" class="ml-n3">{{ t.receipts.title }}</v-btn>
      <v-spacer />
      <v-btn v-if="receipt" variant="text" color="error" prepend-icon="mdi-delete-outline" @click="confirmDelete = true">{{ t.common.delete }}</v-btn>
    </div>
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
                <v-chip v-if="receipt.source === 'email'" variant="outlined" prepend-icon="mdi-email-outline" label>{{ t.receipts.sources.email }}</v-chip>
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
                <v-chip v-if="l.bottles" variant="tonal" prepend-icon="mdi-bottle-soda-classic-outline" label>{{ t.receipts.bottles(l.bottles) }}</v-chip>
                <template v-else-if="l.product_id != null">
                  <v-chip color="primary" variant="tonal" prepend-icon="mdi-link-variant" label>{{ productsById.get(l.product_id)?.name ?? `#${l.product_id}` }}</v-chip>
                  <v-chip v-if="l.method" :color="methodColor[l.method] ?? 'grey'" variant="outlined" label>
                    {{ t.receipts.methods[l.method] ?? l.method }}<template v-if="l.method === 'fuzzy' || l.confidence < 1"> · {{ Math.round(l.confidence * 100) }} %</template>
                  </v-chip>
                </template>
                <v-chip v-else color="warning" variant="tonal" prepend-icon="mdi-link-variant-off" label>{{ t.receipts.unmatchedLine }}</v-chip>
                <v-chip
                  v-if="l.kind === 'item' && (l.pieces ?? 1) !== 1"
                  variant="tonal"
                  color="secondary"
                  prepend-icon="mdi-package-variant"
                  label
                  :disabled="receipt.stocked"
                  :title="t.receipts.pieces"
                  @click="editPieces(l)"
                >
                  {{ t.receipts.piecesChip(formatNumber(l.pieces ?? 1)) }}
                  <template v-if="l.pieces_source && (l.pieces ?? 1) !== 1"> · {{ t.receipts.piecesSources[l.pieces_source] }}</template>
                </v-chip>
                <v-spacer />
                <template v-if="l.kind === 'item'">
                  <v-btn
                    v-if="!receipt.stocked && (l.pieces ?? 1) === 1"
                    size="small"
                    variant="text"
                    icon="mdi-package-variant-plus"
                    :title="t.receipts.pieces"
                    :aria-label="t.receipts.pieces"
                    @click="editPieces(l)"
                  />
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
      <v-dialog v-model="piecesOpen" max-width="420">
        <v-card v-if="piecesLine" :title="t.receipts.pieces" :subtitle="piecesLine.raw_text">
          <v-card-text>
            <div class="text-body-2 text-medium-emphasis mb-4">{{ t.receipts.piecesHint }}</div>
            <v-text-field v-model="piecesValue" :label="t.receipts.pieces" inputmode="decimal" autofocus @keydown.enter="savePieces">
              <template #prepend-inner><v-btn icon="mdi-minus" size="x-small" variant="tonal" :disabled="piecesNumber <= 1" @click="piecesValue = Math.max(1, piecesNumber - 1)" /></template>
              <template #append-inner><v-btn icon="mdi-plus" size="x-small" variant="tonal" @click="piecesValue = (piecesNumber || 0) + 1" /></template>
            </v-text-field>
            <div class="d-flex flex-wrap ga-1 mb-3">
              <v-chip v-for="n in [1, 4, 6, 8, 12, 20, 24]" :key="n" size="small" :variant="piecesNumber === n ? 'flat' : 'tonal'" :color="piecesNumber === n ? 'primary' : undefined" @click="piecesValue = n">{{ n }}</v-chip>
            </div>
            <div v-if="piecesNumber > 0" class="text-body-2">{{ t.receipts.piecesStock(formatNumber((piecesLine.qty || 1) * piecesNumber)) }}</div>
            <div class="text-caption text-medium-emphasis mt-1">{{ t.receipts.piecesRemember }}</div>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="piecesOpen = false">{{ t.common.cancel }}</v-btn>
            <v-btn color="primary" variant="flat" :loading="savingPieces" :disabled="!(piecesNumber > 0)" @click="savePieces">{{ t.common.save }}</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </template>
    <ConfirmDialog
      v-model="confirmDelete"
      :title="t.receipts.deleteTitle"
      :text="receipt?.stocked ? t.receipts.deleteStocked : t.receipts.deleteText"
      @confirm="remove"
    />
  </div>
</template>
