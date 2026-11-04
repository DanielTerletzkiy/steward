<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import type { BluetoothDevice } from '@/types'

// Pair a Bluetooth barcode scanner with the Pi, from the kiosk screen. The page can't do that itself
// (browsers don't pair keyboard-like devices), so it sends commands through Steward to the helper the
// setup script installed on the Pi (kiosk/steward-kiosk-agent).
const helper = ref<'checking' | 'online' | 'offline' | 'no-bluetooth'>('checking')
const paired = ref<BluetoothDevice[]>([])
const found = ref<BluetoothDevice[] | null>(null)
const busy = ref<string | null>(null) // what is running: 'status' | 'scan' | an address
const error = ref<string | null>(null)
const success = ref<string | null>(null)

/** Send a command and wait for the helper's answer. */
async function run<T>(type: string, args: Record<string, unknown> = {}, seconds = 60): Promise<T> {
  let command = await api.agentCommand(type, args)
  const end = Date.now() + seconds * 1000
  while (command.status === 'pending' || command.status === 'running') {
    if (Date.now() > end) throw new Error(t.kiosk.bt.timeout)
    await new Promise((r) => setTimeout(r, 1000))
    command = await api.agentCommandStatus(command.id)
  }
  if (command.status === 'failed') throw new Error(command.error ?? t.kiosk.failed)
  return command.result as T
}

async function refresh() {
  error.value = null
  busy.value = 'status'
  try {
    const agent = await api.kioskAgent()
    if (!agent.connected) {
      helper.value = 'offline'
      return
    }
    if (agent.info.bluetooth === false) {
      helper.value = 'no-bluetooth'
      return
    }
    helper.value = 'online'
    paired.value = (await run<{ devices: BluetoothDevice[] }>('bt_status', {}, 20)).devices
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = null
  }
}
onMounted(refresh)

async function scan() {
  error.value = null
  success.value = null
  busy.value = 'scan'
  try {
    found.value = (await run<{ devices: BluetoothDevice[] }>('bt_scan', { seconds: 12 }, 45)).devices.filter((d) => !d.paired)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = null
  }
}

async function pair(d: BluetoothDevice) {
  error.value = null
  success.value = null
  busy.value = d.address
  try {
    await run('bt_pair', { address: d.address }, 90)
    success.value = t.kiosk.bt.paired(d.name ?? d.address)
    found.value = found.value?.filter((f) => f.address !== d.address) ?? null
    await refresh()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = null
  }
}

async function remove(d: BluetoothDevice) {
  error.value = null
  busy.value = d.address
  try {
    await run('bt_remove', { address: d.address }, 20)
    await refresh()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = null
  }
}

const isInput = (d: BluetoothDevice) => (d.icon ?? '').startsWith('input')
const deviceIcon = (d: BluetoothDevice) => (isInput(d) ? 'mdi-barcode-scan' : 'mdi-bluetooth')
const named = computed(() => (found.value ?? []).filter((d) => d.name))
</script>

<template>
  <div>
    <p class="text-body-1 text-medium-emphasis mb-4">{{ t.kiosk.bt.intro }}</p>

    <v-progress-linear v-if="helper === 'checking'" indeterminate color="primary" class="mb-4" />
    <v-alert v-else-if="helper === 'offline'" type="warning" variant="tonal" class="mb-4" :title="t.kiosk.bt.noHelper" :text="t.kiosk.bt.noHelperHint">
      <template #append><v-btn variant="text" @click="refresh">{{ t.app.retry }}</v-btn></template>
    </v-alert>
    <v-alert v-else-if="helper === 'no-bluetooth'" type="warning" variant="tonal" class="mb-4" :text="t.kiosk.bt.noBluetooth" />

    <template v-if="helper === 'online'">
      <div class="text-overline text-medium-emphasis">{{ t.kiosk.bt.pairedTitle }}</div>
      <div v-if="!paired.length" class="text-body-1 text-medium-emphasis mb-3">{{ t.kiosk.bt.nonePaired }}</div>
      <v-list v-else class="bg-transparent mb-3">
        <v-list-item v-for="d in paired" :key="d.address" :title="d.name ?? d.address" :subtitle="d.connected ? t.kiosk.bt.connected : t.kiosk.bt.notConnected" :prepend-icon="deviceIcon(d)">
          <template #append>
            <v-btn variant="text" color="error" :loading="busy === d.address" :disabled="!!busy && busy !== d.address" @click="remove(d)">{{ t.kiosk.bt.remove }}</v-btn>
          </template>
        </v-list-item>
      </v-list>

      <v-btn color="primary" variant="flat" size="x-large" prepend-icon="mdi-bluetooth-connect" :loading="busy === 'scan'" :disabled="!!busy && busy !== 'scan'" @click="scan">
        {{ t.kiosk.bt.search }}
      </v-btn>
      <div v-if="busy === 'scan'" class="text-body-1 text-medium-emphasis mt-2">{{ t.kiosk.bt.searching }}</div>

      <template v-if="found && busy !== 'scan'">
        <div class="text-overline text-medium-emphasis mt-4">{{ t.kiosk.bt.foundTitle }}</div>
        <div v-if="!named.length" class="text-body-1 text-medium-emphasis">{{ t.kiosk.bt.noneFound }}</div>
        <v-list v-else class="bg-transparent">
          <v-list-item v-for="d in named" :key="d.address" :title="d.name ?? d.address" :subtitle="isInput(d) ? t.kiosk.bt.looksLikeScanner : d.address" :prepend-icon="deviceIcon(d)">
            <template #append>
              <v-btn :variant="isInput(d) ? 'flat' : 'tonal'" color="primary" size="large" :loading="busy === d.address" :disabled="!!busy && busy !== d.address" @click="pair(d)">
                {{ t.kiosk.bt.pair }}
              </v-btn>
            </template>
          </v-list-item>
        </v-list>
      </template>
    </template>

    <v-alert v-if="success" type="success" variant="tonal" class="mt-4" :text="success" />
    <v-alert v-if="error" type="error" variant="tonal" class="mt-4" :text="error" />
  </div>
</template>
