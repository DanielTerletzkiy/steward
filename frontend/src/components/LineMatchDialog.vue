<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { formatEuro } from '@/composables/format'
import { useCatalog } from '@/composables/catalog'
import { attempt, notify } from '@/composables/notify'
import type { ReceiptLine } from '@/types'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ receiptId: number; line: ReceiptLine | null }>()
const emit = defineEmits<{ saved: [] }>()
const { state, categories, units } = useCatalog()

const tab = ref<'existing' | 'new'>('existing')
const productId = ref<number | null>(null)
const draft = ref({ name: '', category: null as string | null, location_id: null as number | null, unit: 'Stk', due_days: null as number | null })
const busy = ref(false)

function prettify(raw: string) {
  return raw
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/(^|[\s-])(\p{L})/gu, (_m, sep: string, ch: string) => sep + ch.toUpperCase())
}

watch(open, (v) => {
  if (!v || !props.line) return
  productId.value = props.line.product_id
  tab.value = 'existing'
  draft.value = { name: prettify(props.line.raw_text), category: null, location_id: null, unit: props.line.unit || 'Stk', due_days: null }
})

async function save() {
  if (!props.line) return
  busy.value = true
  const lineId = props.line.id
  const res = await attempt(() => {
    if (tab.value === 'existing') {
      if (productId.value == null) throw new Error(t.receipts.pickProduct)
      return api.matchLine(props.receiptId, lineId, { product_id: productId.value })
    }
    const d = draft.value
    if (!d.name.trim()) throw new Error(t.common.required)
    return api.matchLine(props.receiptId, lineId, {
      new_product: { name: d.name.trim(), category: d.category || null, location_id: d.location_id, unit: d.unit || 'Stk', due_days: d.due_days ?? null },
    })
  })
  busy.value = false
  if (res) {
    notify(t.receipts.lineMatched)
    emit('saved')
    open.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" max-width="520" scrollable>
    <v-card v-if="line" prepend-icon="mdi-link-variant">
      <template #title>{{ t.receipts.pickTitle }}</template>
      <template #subtitle>
        <span class="font-weight-medium" style="font-family: monospace">{{ line.raw_text }}</span> · {{ formatEuro(line.total) }}
      </template>
      <v-tabs v-model="tab" grow color="primary">
        <v-tab value="existing" prepend-icon="mdi-magnify">{{ t.receipts.existing }}</v-tab>
        <v-tab value="new" prepend-icon="mdi-plus">{{ t.receipts.createNew }}</v-tab>
      </v-tabs>
      <v-card-text style="min-height: 240px">
        <v-window v-model="tab">
          <v-window-item value="existing">
            <v-autocomplete
              v-model="productId"
              :items="state.products"
              item-title="name"
              item-value="id"
              :label="t.receipts.pickProduct"
              prepend-inner-icon="mdi-magnify"
              autofocus
              clearable
              auto-select-first
            >
              <template #item="{ props: itemProps, item }">
                <v-list-item v-bind="itemProps" :subtitle="[item.raw.brand, item.raw.category].filter(Boolean).join(' · ')" />
              </template>
            </v-autocomplete>
          </v-window-item>
          <v-window-item value="new">
            <v-text-field v-model="draft.name" :label="t.common.name" />
            <v-row dense>
              <v-col cols="12" sm="6"><v-combobox v-model="draft.category" :label="t.common.category" :items="categories" /></v-col>
              <v-col cols="12" sm="6">
                <v-select v-model="draft.location_id" :label="t.common.location" :items="state.locations" item-title="name" item-value="id" clearable />
              </v-col>
              <v-col cols="6"><v-combobox v-model="draft.unit" :label="t.common.unit" :items="units" /></v-col>
              <v-col cols="6"><v-text-field v-model.number="draft.due_days" :label="t.stock.dueDays" type="number" min="0" clearable /></v-col>
            </v-row>
          </v-window-item>
        </v-window>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="open = false">{{ t.common.cancel }}</v-btn>
        <v-btn color="primary" variant="flat" :loading="busy" @click="save">{{ tab === 'new' ? t.common.create : t.common.save }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
