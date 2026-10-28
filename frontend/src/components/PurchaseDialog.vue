<script setup lang="ts">
import { ref, watch } from 'vue'
import { t } from '@/i18n'
import { addDays, todayIso } from '@/composables/format'
import { useCatalog } from '@/composables/catalog'
import { purchase } from '@/composables/stockActions'
import type { Product } from '@/types'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ product: Product | null }>()
const { state } = useCatalog()

const amount = ref(1)
const dueDate = ref<string | null>(null)
const price = ref<string>('')
const locationId = ref<number | null>(null)
const busy = ref(false)

watch(open, (v) => {
  if (!v || !props.product) return
  amount.value = 1
  dueDate.value = props.product.due_days != null ? addDays(todayIso(), props.product.due_days) : null
  price.value = ''
  locationId.value = props.product.location_id
})

async function submit() {
  if (!props.product || amount.value <= 0) return
  busy.value = true
  const p = price.value.trim() ? Number(price.value.replace(',', '.')) : null
  const ok = await purchase(props.product, Number(amount.value), {
    due_date: dueDate.value || null,
    location_id: locationId.value,
    unit_price: p != null && !Number.isNaN(p) ? p : null,
  })
  busy.value = false
  if (ok) open.value = false
}
</script>

<template>
  <v-dialog v-model="open" max-width="440">
    <v-card v-if="product" :title="t.stock.purchaseTitle(product.name)" prepend-icon="mdi-cart-plus">
      <v-card-text>
        <v-form @submit.prevent="submit">
          <v-text-field v-model.number="amount" :label="t.common.amount" type="number" min="0" step="any" :suffix="product.unit" autofocus />
          <v-text-field v-model="dueDate" :label="t.common.dueDate" type="date" clearable :hint="product.due_type === 'expiration' ? t.stock.expiration : t.stock.bestBefore" persistent-hint class="mb-2" />
          <v-select v-model="locationId" :label="t.common.location" :items="state.locations" item-title="name" item-value="id" clearable />
          <v-text-field v-model="price" :label="t.stock.unitPrice" inputmode="decimal" prepend-inner-icon="mdi-currency-eur" :hint="t.common.optional" persistent-hint />
          <button type="submit" hidden />
        </v-form>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="open = false">{{ t.common.cancel }}</v-btn>
        <v-btn color="primary" variant="flat" :loading="busy" @click="submit">{{ t.common.add }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
