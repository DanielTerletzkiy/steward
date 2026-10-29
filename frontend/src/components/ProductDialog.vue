<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { useCatalog } from '@/composables/catalog'
import { attempt, notify } from '@/composables/notify'
import ConfirmDialog from './ConfirmDialog.vue'
import type { Product, ProductIn } from '@/types'
import LocationSelect from './LocationSelect.vue'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ product?: Product | null; initialName?: string }>()
const emit = defineEmits<{ saved: [Product] }>()
const { categories, units } = useCatalog()

const empty = (): ProductIn & { aliases: string } => ({
  name: '', brand: null, category: null, location_id: null, unit: 'Stk', min_stock: 0, due_days: null, due_type: 'best_before', aliases: '',
})
const form = ref(empty())
const busy = ref(false)
const requiredRule = [(v: string | null) => !!v?.trim() || t.common.required]
const confirmDelete = ref(false)
const isEdit = computed(() => !!props.product)

watch(open, (v) => {
  if (!v) return
  const p = props.product
  form.value = p
    ? { name: p.name, brand: p.brand, category: p.category, location_id: p.location_id, unit: p.unit, min_stock: p.min_stock, due_days: p.due_days, due_type: p.due_type, aliases: '' }
    : { ...empty(), name: props.initialName ?? '' }
})

const dueTypes = [
  { title: t.stock.bestBefore, value: 'best_before' },
  { title: t.stock.expiration, value: 'expiration' },
]

async function save() {
  const f = form.value
  if (!f.name.trim()) return
  busy.value = true
  const body: ProductIn = {
    name: f.name.trim(),
    brand: f.brand || null,
    category: f.category || null,
    location_id: f.location_id ?? null,
    unit: f.unit || 'Stk',
    min_stock: Number(f.min_stock) || 0,
    due_days: f.due_days === null || (f.due_days as unknown) === '' ? null : Number(f.due_days),
    due_type: f.due_type,
  }
  const result = await attempt(() => {
    if (props.product) return api.updateProduct(props.product.id, body)
    const aliases = f.aliases.split(',').map((s) => s.trim()).filter(Boolean)
    return api.createProduct({ ...body, receipt_aliases: aliases })
  })
  busy.value = false
  if (result) {
    notify(t.stock.productSaved)
    emit('saved', result)
    open.value = false
  }
}

async function remove() {
  if (!props.product) return
  const ok = await attempt(async () => {
    await api.deleteProduct(props.product!.id)
    return true
  })
  if (ok) {
    notify(t.stock.productDeleted)
    open.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" max-width="560" scrollable>
    <v-card :title="isEdit ? t.stock.editProduct : t.stock.newProduct" :prepend-icon="isEdit ? 'mdi-pencil' : 'mdi-plus'">
      <v-card-text>
        <v-form @submit.prevent="save">
          <v-text-field v-model="form.name" :label="t.common.name" :rules="requiredRule" autofocus />
          <v-row dense>
            <v-col cols="12" sm="6"><v-text-field v-model="form.brand" :label="t.common.brand" /></v-col>
            <v-col cols="12" sm="6"><v-combobox v-model="form.category" :label="t.common.category" :items="categories" /></v-col>
            <v-col cols="12" sm="6">
              <LocationSelect v-model="form.location_id" />
            </v-col>
            <v-col cols="12" sm="6"><v-combobox v-model="form.unit" :label="t.common.unit" :items="units" /></v-col>
            <v-col cols="6"><v-text-field v-model.number="form.min_stock" :label="t.stock.minStock" type="number" min="0" step="any" /></v-col>
            <v-col cols="6"><v-text-field v-model.number="form.due_days" :label="t.stock.dueDays" type="number" min="0" clearable /></v-col>
            <v-col cols="12"><v-select v-model="form.due_type" :label="t.stock.dueType" :items="dueTypes" /></v-col>
            <v-col v-if="!isEdit" cols="12">
              <v-text-field v-model="form.aliases" :label="t.stock.aliases" :hint="t.stock.aliasesHint" persistent-hint />
            </v-col>
          </v-row>
          <button type="submit" hidden />
        </v-form>
      </v-card-text>
      <v-card-actions>
        <v-btn v-if="isEdit" color="error" prepend-icon="mdi-delete-outline" @click="confirmDelete = true">{{ t.common.delete }}</v-btn>
        <v-spacer />
        <v-btn @click="open = false">{{ t.common.cancel }}</v-btn>
        <v-btn color="primary" variant="flat" :loading="busy" @click="save">{{ isEdit ? t.common.save : t.common.create }}</v-btn>
      </v-card-actions>
    </v-card>
    <ConfirmDialog v-if="product" v-model="confirmDelete" :title="t.stock.deleteProduct" :text="t.stock.confirmDelete(product.name)" @confirm="remove" />
  </v-dialog>
</template>
