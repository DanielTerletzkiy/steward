<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { t } from '@/i18n'
import { appCall, type AppFailure, type AppInfo } from '@/composables/kioskApp'
import type { BluetoothDevice } from '@/types'

// The terminal's own settings, from the Steward Kiosk app on the Pi: pairing Bluetooth scanners (a web
// page can't pair them), the app's version and Steward's address.
const info = ref<AppInfo | null>(null)
const powered = ref(true)
const paired = ref<BluetoothDevice[]>([])
const found = ref<BluetoothDevice[] | null>(null)
const busy = ref<string | null>(null) // what is running: 'status' | 'scan' | an address
const error = ref<string | null>(null)
const success = ref<string | null>(null)

function explain(e: unknown): string {
  const failure = e as Partial<AppFailure> | null
  if (failure && typeof failure === 'object' && failure.code) {
    return t.kiosk.bt.errors[failure.code] ?? failure.detail ?? t.kiosk.failed
  }
  return e instanceof Error ? e.message : String(e)
}

/** Run a Bluetooth command; `what` marks the button that shows a spinner. */
async function run<T>(what: string, cmd: string, args?: Record<string, unknown>): Promise<T | null> {
  error.value = null
  busy.value = what
  try {
    return await appCall<T>(cmd, args)
  } catch (e) {
    error.value = explain(e)
    return null
  } finally {
    busy.value = null
  }
}

async function refresh() {
  const status = await run<{ powered: boolean; devices: BluetoothDevice[] }>('status', 'bt_status')
  if (status) {
    powered.value = status.powered
    paired.value = status.devices
  }
}

onMounted(async () => {
  info.value = await appCall<AppInfo>('kiosk_info').catch(() => null)
  if (info.value?.bluetooth) await refresh()
})

async function scan() {
  success.value = null
  const devices = await run<BluetoothDevice[]>('scan', 'bt_scan', { seconds: 12 })
  if (devices) found.value = devices.filter((d) => !d.paired)
}

async function pair(d: BluetoothDevice) {
  success.value = null
  if (await run<BluetoothDevice>(d.address, 'bt_pair', { address: d.address })) {
    success.value = t.kiosk.bt.paired(d.name ?? d.address)
    found.value = found.value?.filter((f) => f.address !== d.address) ?? null
    await refresh()
  }
}

async function remove(d: BluetoothDevice) {
  await run(d.address, 'bt_remove', { address: d.address })
  await refresh()
}

const isInput = (d: BluetoothDevice) => (d.icon ?? '').startsWith('input')
const deviceIcon = (d: BluetoothDevice) => (isInput(d) ? 'mdi-barcode-scan' : 'mdi-bluetooth')
const named = computed(() => (found.value ?? []).filter((d) => d.name))
</script>

<template>
  <div>
    <v-progress-linear v-if="!info" indeterminate color="primary" class="mb-4" />

    <template v-else>
      <div class="text-h6 mb-1">{{ t.kiosk.bt.title }}</div>
      <p class="text-body-1 text-medium-emphasis mb-4">{{ t.kiosk.bt.intro }}</p>
      <v-alert v-if="!info.bluetooth" type="warning" variant="tonal" class="mb-4" :text="t.kiosk.bt.noBluetooth" />

      <template v-else>
        <v-alert v-if="!powered" type="warning" variant="tonal" class="mb-4" :text="t.kiosk.bt.errors.blocked" />
        <div class="text-overline text-medium-emphasis">{{ t.kiosk.bt.pairedTitle }}</div>
        <v-progress-linear v-if="busy === 'status'" indeterminate color="primary" class="mb-3" />
        <div v-else-if="!paired.length" class="text-body-1 text-medium-emphasis mb-3">{{ t.kiosk.bt.nonePaired }}</div>
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

      <v-divider class="my-5" />
      <div class="d-flex align-center flex-wrap ga-3">
        <div class="text-body-1 text-medium-emphasis flex-grow-1">{{ t.kiosk.terminal.version(info.version) }}</div>
        <v-btn variant="tonal" size="large" prepend-icon="mdi-web" @click="appCall('open_setup')">{{ t.kiosk.terminal.changeAddress }}</v-btn>
      </div>
    </template>
  </div>
</template>
