<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { attempt } from '@/composables/notify'
import type { ShoppingItem } from '@/types'

// Edit a shopping list entry: what, how many, and a note (e.g. "the organic one").
const open = defineModel<boolean>({ default: false })
const props = defineProps<{ item: ShoppingItem | null; unit?: string | null }>()
const emit = defineEmits<{ saved: [ShoppingItem] }>()

const form = ref({ text: '', amount: 1 as number | string, note: '' })
const busy = ref(false)
const requiredRule = [(v: string | null) => !!v?.trim() || t.common.required]
const amountRule = [(v: number | string) => Number(v) > 0 || t.shopping.amountPositive]

watch(open, (v) => {
  const item = props.item
  if (!v || !item) return
  form.value = { text: item.text, amount: item.amount, note: item.note ?? '' }
})

async function save() {
  const item = props.item
  const f = form.value
  const amount = Number(String(f.amount).replace(',', '.'))
  if (!item || !f.text.trim() || !(amount > 0)) return
  busy.value = true
  const res = await attempt(() => api.updateShoppingItem(item.id, { text: f.text.trim(), amount, note: f.note.trim() || null }))
  busy.value = false
  if (res) {
    emit('saved', res)
    open.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" max-width="460">
    <v-card :title="t.shopping.edit" prepend-icon="mdi-pencil">
      <v-card-text>
        <v-form @submit.prevent="save">
          <v-text-field v-model="form.text" :label="t.common.name" :rules="requiredRule" autofocus />
          <v-text-field v-model="form.amount" :label="t.shopping.amount" :suffix="unit ?? ''" inputmode="decimal" :rules="amountRule" />
          <v-text-field v-model="form.note" :label="t.common.notes" :placeholder="t.shopping.notePlaceholder" />
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
