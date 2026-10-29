<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { useResource } from '@/composables/resource'
import { attempt, notify } from '@/composables/notify'
import { relativeTime } from '@/composables/format'
import ConfirmDialog from './ConfirmDialog.vue'
import ModeCardsDialog from './ModeCardsDialog.vue'
import type { Terminal, TerminalPairing } from '@/types'

// Settings: kitchen terminals (a Raspberry Pi with a scanner, a wall tablet). Pair, re-pair, remove.
const SETUP_SCRIPT = 'https://github.com/DanielTerletzkiy/steward/releases/latest/download/setup-pi.sh'
const PAIR_MINUTES = 15

const { data } = useResource(() => api.terminals(), ['terminals'], null)

// Where the terminal reaches Steward: the app's host port (the server knows it), or this page's own
// address when it isn't opened through Home Assistant's sidebar.
const inIngress = window.location.pathname.includes('/api/hassio_ingress/')
const base = computed(() => {
  if (data.value?.direct_url) return `${data.value.direct_url.replace(/\/$/, '')}/`
  if (inIngress) return null
  const url = new URL('.', window.location.href)
  url.hash = ''
  url.search = ''
  return url.toString()
})

const adding = ref(false)
const name = ref('')
const busy = ref(false)
async function add() {
  const value = name.value.trim() || t.terminals.namePlaceholder
  busy.value = true
  const res = await attempt(() => api.createTerminal(value))
  busy.value = false
  if (!res) return
  adding.value = false
  name.value = ''
  pairing.value = res
}

const pairing = ref<TerminalPairing | null>(null)
async function newCode(terminal: Terminal) {
  const res = await attempt(() => api.newPairingCode(terminal.id))
  if (res) pairing.value = res
}
const pairLink = computed(() => (pairing.value && base.value ? `${base.value}auth/terminal?code=${encodeURIComponent(pairing.value.code)}` : null))
const kioskUrl = computed(() => (base.value ? `${base.value}#/kiosk` : null))
const setupCommand = computed(() => (pairLink.value ? `curl -fsSL ${SETUP_SCRIPT} | bash -s -- '${pairLink.value}'` : null))

async function copy(text: string, event: Event) {
  try {
    await navigator.clipboard.writeText(text)
    notify(t.terminals.copied)
  } catch {
    // No clipboard outside HTTPS: select the text so it can be copied by hand.
    const field = (event.currentTarget as HTMLElement).closest('.v-field')?.querySelector('input, textarea') as HTMLInputElement | null
    field?.select()
  }
}

const removing = ref<Terminal | null>(null)
async function remove(terminal: Terminal) {
  const done = await attempt(async () => {
    await api.deleteTerminal(terminal.id)
    return true
  })
  if (done) notify(t.terminals.removed)
}

const cardsOpen = ref(false)
</script>

<template>
  <v-card variant="flat" border class="mb-6">
    <v-list v-if="data?.terminals.length" lines="two" bg-color="transparent">
      <v-list-item v-for="terminal in data.terminals" :key="terminal.id" :title="terminal.name">
        <template #prepend>
          <v-avatar :color="terminal.paired ? 'primary' : undefined" variant="tonal"><v-icon icon="mdi-monitor-dashboard" /></v-avatar>
        </template>
        <v-list-item-subtitle>
          {{ terminal.paired ? t.terminals.paired : t.terminals.waiting }}<template v-if="terminal.last_seen"> · {{ t.terminals.lastSeen(relativeTime(terminal.last_seen)) }}</template>
        </v-list-item-subtitle>
        <template #append>
          <v-btn variant="text" size="small" prepend-icon="mdi-link-variant" @click="newCode(terminal)">{{ t.terminals.newCode }}</v-btn>
          <v-btn variant="text" size="small" icon="mdi-delete-outline" :title="t.terminals.remove" @click="removing = terminal" />
        </template>
      </v-list-item>
    </v-list>
    <v-card-text v-else class="text-medium-emphasis">{{ t.terminals.empty }}</v-card-text>
    <v-card-actions class="px-4 pb-4 flex-wrap ga-2">
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="adding = true">{{ t.terminals.add }}</v-btn>
      <v-btn variant="tonal" prepend-icon="mdi-printer-outline" @click="cardsOpen = true">{{ t.terminals.modeCards }}</v-btn>
    </v-card-actions>
  </v-card>

  <v-dialog v-model="adding" max-width="420">
    <v-card :title="t.terminals.add">
      <v-card-text>
        <v-text-field v-model="name" :label="t.terminals.name" :placeholder="t.terminals.namePlaceholder" autofocus hide-details @keydown.enter="add" />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="adding = false">{{ t.common.cancel }}</v-btn>
        <v-btn color="primary" variant="flat" :loading="busy" @click="add">{{ t.common.create }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-dialog :model-value="!!pairing" max-width="640" @update:model-value="pairing = null">
    <v-card v-if="pairing" :title="t.terminals.codeTitle(pairing.terminal.name)">
      <v-card-text>
        <p class="text-body-2 text-medium-emphasis mb-4">{{ t.terminals.codeText(PAIR_MINUTES) }}</p>
        <div class="pair-code text-center mb-5">{{ pairing.code }}</div>
        <v-alert v-if="!base" type="warning" variant="tonal" density="compact" :text="t.terminals.noDirectUrl" />
        <template v-else>
          <v-text-field :model-value="kioskUrl" :label="t.terminals.address" readonly variant="outlined" density="comfortable" class="mb-3" hide-details>
            <template #append-inner><v-btn icon="mdi-content-copy" variant="text" size="small" :title="t.terminals.copy" @click="copy(kioskUrl!, $event)" /></template>
          </v-text-field>
          <div class="text-subtitle-2 mt-4">{{ t.terminals.setup }}</div>
          <div class="text-body-2 text-medium-emphasis mb-2">{{ t.terminals.setupHint }}</div>
          <v-textarea :model-value="setupCommand" readonly variant="outlined" rows="3" auto-grow hide-details class="setup-command">
            <template #append-inner><v-btn icon="mdi-content-copy" variant="text" size="small" :title="t.terminals.copy" @click="copy(setupCommand!, $event)" /></template>
          </v-textarea>
        </template>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn color="primary" variant="flat" @click="pairing = null">{{ t.common.done }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <ConfirmDialog
    :model-value="!!removing"
    :title="t.terminals.remove"
    :text="removing ? t.terminals.confirmRemove(removing.name) : ''"
    :confirm-label="t.terminals.remove"
    @update:model-value="removing = null"
    @confirm="removing && remove(removing)"
  />
  <ModeCardsDialog v-model="cardsOpen" />
</template>

<style scoped>
.pair-code {
  font-family: ui-monospace, monospace;
  font-size: 2.5rem;
  font-weight: 700;
  letter-spacing: 0.12em;
}
.setup-command :deep(textarea) {
  font-family: ui-monospace, monospace;
  font-size: 0.85rem;
}
</style>
