<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { useResource } from '@/composables/resource'
import { useCatalog } from '@/composables/catalog'
import { mdiIcon, parseDateTime, relativeDue } from '@/composables/format'
import { useKiosk } from '@/composables/kiosk'
import type { Chore } from '@/types'

// Kiosk "Stock" tab, right side: chores, overdue and today first. Done asks who did it.
const kiosk = useKiosk()
const { state, personName } = useCatalog()
const { data: chores } = useResource<Chore[]>(() => api.chores(), ['chores', 'people'], [])

const ORDER: Record<string, number> = { overdue: 0, due_today: 1, due_soon: 2, scheduled: 3, manual: 4 }
const COLOR: Record<string, string | undefined> = { overdue: 'error', due_today: 'warning', due_soon: 'info' }
const sorted = computed(() =>
  [...chores.value].sort((a, b) => (ORDER[a.status] ?? 9) - (ORDER[b.status] ?? 9) || (a.next_due ?? '9').localeCompare(b.next_due ?? '9')),
)
const dueText = (c: Chore) => (c.next_due ? relativeDue(parseDateTime(c.next_due)) : t.status.manual)

const doing = ref<Chore | null>(null)
const busy = ref(false)
async function done(c: Chore, personId: string | null) {
  busy.value = true
  try {
    await api.executeChore(c.id, { person_id: personId })
    doing.value = null
    kiosk.signal('ok', t.chores.doneMsg(c.name))
  } catch (e) {
    kiosk.signal('error', e instanceof Error ? e.message : t.kiosk.failed)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div>
    <div class="text-h5 font-weight-bold mb-3">{{ t.chores.title }}</div>
    <div v-if="!sorted.length" class="text-body-1 text-medium-emphasis">{{ t.chores.empty }}</div>
    <v-card v-else variant="flat" border>
      <template v-for="(c, n) in sorted" :key="c.id">
        <v-divider v-if="n > 0" />
        <v-list-item class="kiosk-chores__row">
          <template #prepend>
            <v-avatar :color="COLOR[c.status] ?? 'surface-variant'" variant="tonal" size="44"><v-icon :icon="mdiIcon(c.icon)" /></v-avatar>
          </template>
          <v-list-item-title class="text-h6">{{ c.name }}</v-list-item-title>
          <v-list-item-subtitle class="text-body-1">
            <span :class="COLOR[c.status] ? `text-${COLOR[c.status]}` : ''">{{ dueText(c) }}</span>
            <template v-if="c.next_assignee"> · {{ personName(c.next_assignee) }}</template>
          </v-list-item-subtitle>
          <template #append>
            <v-btn
              size="large"
              :variant="c.status === 'overdue' || c.status === 'due_today' ? 'flat' : 'tonal'"
              color="primary"
              prepend-icon="mdi-check"
              @click="state.people.length > 1 ? (doing = c) : done(c, c.next_assignee ?? state.people[0]?.id ?? null)"
            >
              {{ t.common.done }}
            </v-btn>
          </template>
        </v-list-item>
      </template>
    </v-card>

    <v-dialog :model-value="!!doing" max-width="520" @update:model-value="doing = null">
      <v-card v-if="doing" :title="t.kiosk.whoDidIt(doing.name)">
        <v-card-text class="d-flex flex-column ga-3">
          <v-btn
            v-for="p in state.people"
            :key="p.id"
            size="x-large"
            block
            :variant="p.id === doing.next_assignee ? 'flat' : 'tonal'"
            color="primary"
            :loading="busy"
            prepend-icon="mdi-account-check-outline"
            @click="done(doing, p.id)"
          >
            {{ p.name }}
          </v-btn>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn size="large" @click="doing = null">{{ t.common.cancel }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.kiosk-chores__row {
  min-height: 72px;
}
.kiosk-chores__row :deep(.v-list-item-title) {
  white-space: normal;
  line-height: 1.25;
}
</style>
