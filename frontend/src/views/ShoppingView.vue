<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { api } from '@/api'
import { t } from '@/i18n'
import { useResource } from '@/composables/resource'
import { useCatalog } from '@/composables/catalog'
import { onTopics } from '@/composables/live'
import { attempt, notify } from '@/composables/notify'
import { formatAmount } from '@/composables/format'
import EmptyState from '@/components/EmptyState.vue'
import type { ShoppingItem, ShoppingList } from '@/types'

const { smAndUp } = useDisplay()
const { productsById } = useCatalog()
const { data: lists } = useResource<ShoppingList[]>(() => api.shoppingLists(), ['shopping'], [])
const listId = ref<number | null>(null)
watch(lists, (ls) => {
  if (!ls.length) loading.value = false
  if (ls.length && !ls.some((l) => l.id === listId.value)) listId.value = ls[0].id
})

const items = ref<ShoppingItem[]>([])
const loading = ref(true)
async function loadItems() {
  if (listId.value == null) return
  const res = await attempt(() => api.shoppingItems(listId.value!))
  if (res) items.value = res
  loading.value = false
}
watch(listId, loadItems)
onTopics(['shopping'], loadItems)

const open = computed(() => items.value.filter((i) => !i.done))
const done = computed(() => items.value.filter((i) => i.done))
const showDone = ref(true)

const newText = ref('')
const adding = ref(false)
async function add() {
  const text = newText.value.trim()
  if (!text || listId.value == null) return
  adding.value = true
  // "3 Äpfel" -> amount 3, text "Äpfel"
  const m = text.match(/^(\d+(?:[.,]\d+)?)\s*[x×]?\s+(.+)$/)
  const body = m ? { text: m[2], amount: Number(m[1].replace(',', '.')) } : { text }
  const res = await attempt(() => api.addShoppingItem(listId.value!, body))
  adding.value = false
  if (res) {
    newText.value = ''
    items.value = [...items.value, res]
  }
}

async function toggle(item: ShoppingItem) {
  const target = !item.done
  item.done = target // optimistic
  items.value = [...items.value]
  const res = await attempt(() => api.updateShoppingItem(item.id, { done: target }))
  if (!res) loadItems()
}

async function remove(item: ShoppingItem) {
  items.value = items.value.filter((i) => i.id !== item.id)
  const ok = await attempt(async () => {
    await api.deleteShoppingItem(item.id)
    return true
  })
  if (!ok) return loadItems()
  notify(t.shopping.deleted, {
    action: {
      label: t.common.undo,
      run: async () =>
        void (await attempt(() =>
          api.addShoppingItem(item.list_id, { text: item.text, product_id: item.product_id ?? undefined, amount: item.amount, note: item.note ?? undefined }),
        )),
    },
  })
}

async function addMissing() {
  if (listId.value == null) return
  const res = await attempt(() => api.addMissing(listId.value!))
  if (res) notify(t.shopping.added(res.added))
}
async function clearDone() {
  if (listId.value == null) return
  const res = await attempt(() => api.clearDone(listId.value!))
  if (res) notify(t.shopping.removed(res.removed))
}

function amountLabel(i: ShoppingItem) {
  const unit = i.product_id != null ? productsById.value.get(i.product_id)?.unit : undefined
  if (i.amount === 1 && !unit) return ''
  return formatAmount(i.amount, unit)
}
</script>

<template>
  <div class="page" style="max-width: 760px">
    <div class="d-flex align-center mb-4 flex-wrap ga-2">
      <div>
        <div class="page-title">{{ t.shopping.title }}</div>
        <div class="text-body-2 text-medium-emphasis">{{ t.shopping.open(open.length) }}</div>
      </div>
      <v-spacer />
      <v-btn variant="tonal" color="primary" prepend-icon="mdi-cart-arrow-down" @click="addMissing">{{ t.shopping.addMissing }}</v-btn>
      <v-menu v-if="!smAndUp">
        <template #activator="{ props }"><v-btn v-bind="props" icon="mdi-dots-vertical" variant="text" /></template>
        <v-list density="compact">
          <v-list-item prepend-icon="mdi-broom" :title="t.shopping.clearDone" :disabled="!done.length" @click="clearDone" />
        </v-list>
      </v-menu>
      <v-btn v-else variant="text" prepend-icon="mdi-broom" :disabled="!done.length" @click="clearDone">{{ t.shopping.clearDone }}</v-btn>
    </div>

    <v-tabs v-if="lists.length > 1" v-model="listId" color="primary" class="mb-3">
      <v-tab v-for="l in lists" :key="l.id" :value="l.id">{{ l.name }}</v-tab>
    </v-tabs>

    <v-form @submit.prevent="add">
      <v-text-field
        v-model="newText"
        :placeholder="t.shopping.addPlaceholder"
        prepend-inner-icon="mdi-plus"
        variant="solo-filled"
        flat
        rounded="pill"
        hide-details
        :loading="adding"
        class="mb-4"
        @keydown.enter.prevent="add"
      >
        <template #append-inner>
          <v-btn v-if="newText.trim()" icon="mdi-arrow-right" color="primary" variant="flat" size="small" @mousedown.stop @click.stop="add" />
        </template>
      </v-text-field>
    </v-form>

    <v-skeleton-loader v-if="loading" type="list-item@5" class="rounded-xl" />
    <EmptyState v-else-if="!items.length" icon="mdi-cart-outline" :title="t.shopping.empty" :text="t.shopping.emptyHint">
      <v-btn color="primary" variant="tonal" prepend-icon="mdi-cart-arrow-down" @click="addMissing">{{ t.shopping.addMissing }}</v-btn>
    </EmptyState>

    <template v-else>
      <v-card v-if="open.length" variant="flat" border class="mb-4">
        <v-list bg-color="transparent">
          <v-list-item v-for="i in open" :key="i.id" class="clickable" @click="toggle(i)">
            <template #prepend>
              <v-checkbox-btn :model-value="false" color="primary" @click.stop="toggle(i)" />
            </template>
            <v-list-item-title class="wrap">{{ i.text }}</v-list-item-title>
            <v-list-item-subtitle v-if="i.note">{{ i.note }}</v-list-item-subtitle>
            <template #append>
              <span v-if="amountLabel(i)" class="text-body-2 text-medium-emphasis text-tabular mr-2">{{ amountLabel(i) }}</span>
              <v-btn icon="mdi-close" variant="text" size="small" :title="t.common.delete" @click.stop="remove(i)" />
            </template>
          </v-list-item>
        </v-list>
      </v-card>
      <EmptyState v-else compact icon="mdi-check-all" :title="t.shopping.allDone" />

      <div v-if="done.length">
        <v-btn variant="text" :append-icon="showDone ? 'mdi-chevron-up' : 'mdi-chevron-down'" class="mb-2" @click="showDone = !showDone">
          {{ t.shopping.doneSection(done.length) }}
        </v-btn>
        <v-expand-transition>
          <v-card v-if="showDone" variant="flat" border>
            <v-list bg-color="transparent">
              <v-list-item v-for="i in done" :key="i.id" class="clickable" @click="toggle(i)">
                <template #prepend><v-checkbox-btn :model-value="true" color="primary" @click.stop="toggle(i)" /></template>
                <v-list-item-title class="line-through text-medium-emphasis wrap">{{ i.text }}</v-list-item-title>
                <template #append>
                  <v-btn icon="mdi-close" variant="text" size="small" :title="t.common.delete" @click.stop="remove(i)" />
                </template>
              </v-list-item>
            </v-list>
          </v-card>
        </v-expand-transition>
      </div>
    </template>
  </div>
</template>
