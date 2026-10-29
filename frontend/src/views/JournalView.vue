<script setup lang="ts">
import { api } from '@/api'
import { t } from '@/i18n'
import { useResource } from '@/composables/resource'
import { attempt, notify } from '@/composables/notify'
import { formatAmount, formatDateTime, formatEuro } from '@/composables/format'
import { useCatalog } from '@/composables/catalog'
import EmptyState from '@/components/EmptyState.vue'
import type { StockTxn } from '@/types'

const { data: journal, loading } = useResource<StockTxn[]>(() => api.journal(150), ['stock'], [])
const { productsById } = useCatalog()

const typeInfo: Record<string, { icon: string; color: string }> = {
  purchase: { icon: 'mdi-cart-plus', color: 'primary' },
  consume: { icon: 'mdi-silverware-fork-knife', color: 'secondary' },
  spoil: { icon: 'mdi-delete-variant', color: 'error' },
  open: { icon: 'mdi-package-variant-closed-remove', color: 'info' },
  correct: { icon: 'mdi-pencil-outline', color: 'warning' },
}

async function undo(txn: StockTxn) {
  const ok = await attempt(async () => (await api.undo(txn.id), true))
  if (ok) notify(t.common.undone)
}
</script>

<template>
  <div class="page" style="max-width: 800px">
    <div class="page-title mb-4">{{ t.journal.title }}</div>
    <v-skeleton-loader v-if="loading && !journal.length" type="list-item-two-line@6" class="rounded-xl" />
    <EmptyState v-else-if="!journal.length" icon="mdi-history" :title="t.journal.empty" />
    <v-card v-else variant="flat" border>
      <v-list lines="two" bg-color="transparent">
        <v-list-item v-for="txn in journal" :key="txn.id" :class="txn.undone ? 'opacity-50' : ''">
          <template #prepend>
            <v-avatar :color="typeInfo[txn.type]?.color ?? 'grey'" variant="tonal"><v-icon :icon="typeInfo[txn.type]?.icon ?? 'mdi-swap-horizontal'" /></v-avatar>
          </template>
          <v-list-item-title :class="txn.undone ? 'line-through' : ''">
            {{ t.journal.types[txn.type] ?? txn.type }}: {{ txn.product_name }}
          </v-list-item-title>
          <v-list-item-subtitle>
            {{ txn.type === 'correct' && txn.amount > 0 ? '+' : '' }}{{ formatAmount(txn.amount, productsById.get(txn.product_id)?.unit) }}<template v-if="txn.unit_price != null"> · {{ formatEuro(txn.unit_price) }}</template>
            · {{ formatDateTime(txn.at) }} · {{ t.journal.sources[txn.source] ?? txn.source }}<template v-if="txn.actor_name || txn.actor"> · {{ txn.actor_name ?? txn.actor }}</template>
          </v-list-item-subtitle>
          <template #append>
            <v-chip v-if="txn.undone" variant="outlined" label>{{ t.journal.undone }}</v-chip>
            <v-btn v-else-if="txn.type !== 'open'" variant="text" size="small" prepend-icon="mdi-undo" @click="undo(txn)">{{ t.common.undo }}</v-btn>
          </template>
        </v-list-item>
      </v-list>
    </v-card>
  </div>
</template>
