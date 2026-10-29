<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { attempt, notify } from '@/composables/notify'
import type { Product, StockEntry } from '@/types'

// Correct one batch: how much is left, its date and what it cost. Amount changes go into the journal.
const open = defineModel<boolean>({ default: false })
const props = defineProps<{ entry: StockEntry | null; product: Product | null }>()

const form = ref({ amount: '' as number | string, due_date: null as string | null, unit_price: '' as number | string })
const busy = ref(false)
const toNumber = (v: number | string) => (String(v).trim() === '' ? null : Number(String(v).replace(',', '.')))
const amountRule = [(v: number | string) => (toNumber(v) ?? -1) >= 0 || t.common.required]
const priceRule = [(v: number | string) => toNumber(v) === null || (toNumber(v) as number) >= 0 || t.stock.notNegative]

watch(open, (v) => {
  const e = props.entry
  if (!v || !e) return
  form.value = { amount: e.amount, due_date: e.due_date, unit_price: e.unit_price ?? '' }
})

async function save() {
  const e = props.entry
  const amount = toNumber(form.value.amount)
  const price = toNumber(form.value.unit_price)
  if (!e || amount === null || Number.isNaN(amount) || amount < 0 || (price !== null && (Number.isNaN(price) || price < 0))) return
  busy.value = true
  const res = await attempt(() =>
    api.editEntry(e.id, {
      due_date: form.value.due_date || null,
      unit_price: price,
      ...(amount !== e.amount ? { amount } : {}),
    }),
  )
  busy.value = false
  if (res) {
    notify(t.stock.entrySaved)
    open.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" max-width="440">
    <v-card :title="t.stock.editEntry" :subtitle="product?.name" prepend-icon="mdi-pencil">
      <v-card-text>
        <v-form @submit.prevent="save">
          <v-text-field v-model="form.amount" :label="t.stock.amountLeft" :suffix="product?.unit ?? ''" inputmode="decimal" :rules="amountRule" autofocus />
          <v-text-field v-model="form.due_date" type="date" :label="product?.due_type === 'expiration' ? t.stock.expiration : t.stock.bestBefore" clearable />
          <v-text-field v-model="form.unit_price" :label="t.stock.unitPrice" inputmode="decimal" :rules="priceRule" />
          <div class="text-caption text-medium-emphasis">{{ t.stock.entryHint }}</div>
          <button type="submit" hidden />
        </v-form>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="open = false">{{ t.common.cancel }}</v-btn>
        <v-btn color="primary" variant="flat" :loading="busy" @click="save">{{ t.common.save }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
