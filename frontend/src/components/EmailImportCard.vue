<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { useResource } from '@/composables/resource'
import { attempt, notify } from '@/composables/notify'
import { formatDateTime, relativeTime } from '@/composables/format'
import type { EmailImportIn, EmailImportRun, EmailImportSettings } from '@/types'

// Settings: import REWE eBons from a mailbox (IMAP), e.g. Gmail with an app password.
const GMAIL = { host: 'imap.gmail.com', port: 993 }
const { data, reload } = useResource<EmailImportSettings | null>(() => api.emailSettings(), ['settings'], null)

const form = ref({
  provider: 'gmail' as 'gmail' | 'other',
  enabled: false,
  host: GMAIL.host,
  port: GMAIL.port as number | string,
  username: '',
  password: '',
  folder: 'INBOX',
  sender: 'rewe.de',
  mark_read: false,
  interval_minutes: 15,
  since_days: 30,
})
const loaded = ref(false)
watch(
  data,
  (d) => {
    // Fill the form once; later live updates (a check ran) only refresh the status line.
    if (!d || loaded.value) return
    loaded.value = true
    Object.assign(form.value, {
      provider: d.host === GMAIL.host || !d.host ? 'gmail' : 'other',
      enabled: d.enabled,
      host: d.host || GMAIL.host,
      port: d.port || GMAIL.port,
      username: d.username,
      folder: d.folder,
      sender: d.sender,
      mark_read: d.mark_read,
      interval_minutes: d.interval_minutes,
      since_days: d.since_days,
    })
  },
  { immediate: true },
)
watch(
  () => form.value.provider,
  (p) => {
    if (p === 'gmail') Object.assign(form.value, GMAIL)
  },
)

const intervals = computed(() =>
  [15, 30, 60, 180, 720].map((m) => ({ value: m, title: m < 60 ? t.email.minutes(m) : t.email.hours(m / 60) })),
)
const sinceOptions = computed(() => [
  { value: 7, title: t.email.days(7) },
  { value: 30, title: t.email.days(30) },
  { value: 90, title: t.email.days(90) },
  { value: 365, title: t.email.year },
])
const folders = ref<string[]>([])

function body(): EmailImportIn {
  const f = form.value
  return {
    enabled: f.enabled,
    host: f.host.trim(),
    port: Number(f.port) || 993,
    username: f.username.trim(),
    folder: f.folder.trim() || 'INBOX',
    sender: f.sender.trim(),
    mark_read: f.mark_read,
    interval_minutes: f.interval_minutes,
    since_days: f.since_days,
    ...(f.password ? { password: f.password } : {}),
  }
}

const testing = ref(false)
const testResult = ref<{ ok: boolean; text: string } | null>(null)
async function test() {
  testing.value = true
  testResult.value = null
  try {
    const res = await api.testEmail(body())
    folders.value = res.folders
    testResult.value = { ok: true, text: t.email.testOk(res.matches) }
  } catch (e) {
    testResult.value = { ok: false, text: e instanceof Error ? e.message : String(e) }
  } finally {
    testing.value = false
  }
}

const saving = ref(false)
async function save() {
  saving.value = true
  const saved = await attempt(() => api.saveEmailSettings(body()))
  saving.value = false
  if (!saved) return
  form.value.password = ''
  data.value = saved
  notify(t.email.saved)
}

const running = ref(false)
async function runNow() {
  running.value = true
  const saved = await attempt(() => api.saveEmailSettings(body()))
  if (saved) {
    form.value.password = ''
    const res = await attempt(() => api.runEmailImport())
    if (res) notify(resultText(res))
  }
  running.value = false
  reload()
}

function resultText(r: EmailImportRun) {
  const extra = t.email.resultExtra(r.known, r.skipped)
  return t.email.result(r.imported, r.mails) + (extra ? ` · ${extra}` : '')
}
const last = computed(() => data.value?.last_run ?? null)
const canConnect = computed(() => !!form.value.username.trim() && (!!form.value.password || !!data.value?.password_set))
</script>

<template>
  <v-card variant="flat" border class="mb-6">
    <v-card-text>
      <v-btn-toggle v-model="form.provider" mandatory density="comfortable" variant="outlined" divided color="primary" class="mb-4">
        <v-btn value="gmail" prepend-icon="mdi-gmail">{{ t.email.gmail }}</v-btn>
        <v-btn value="other" prepend-icon="mdi-email-outline">{{ t.email.other }}</v-btn>
      </v-btn-toggle>

      <v-alert v-if="form.provider === 'gmail'" type="info" variant="tonal" density="compact" class="mb-4">
        {{ t.email.gmailHelp }}
        <template #append>
          <v-btn href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener" variant="text" size="small" append-icon="mdi-open-in-new">App passwords</v-btn>
        </template>
      </v-alert>

      <v-row dense>
        <v-col cols="12" sm="6">
          <v-text-field v-model="form.username" :label="t.email.address" type="email" autocomplete="off" />
        </v-col>
        <v-col cols="12" sm="6">
          <v-text-field
            v-model="form.password"
            :label="t.email.password"
            type="password"
            autocomplete="new-password"
            :placeholder="data?.password_set ? '••••••••••••••••' : ''"
            :hint="data?.password_set ? t.email.passwordKeep : ''"
            persistent-hint
          />
        </v-col>
        <template v-if="form.provider === 'other'">
          <v-col cols="8"><v-text-field v-model="form.host" :label="t.email.host" placeholder="imap.gmx.net" /></v-col>
          <v-col cols="4"><v-text-field v-model="form.port" :label="t.email.port" inputmode="numeric" /></v-col>
        </template>
        <v-col cols="12" sm="6">
          <v-combobox v-model="form.folder" :items="folders" :label="t.email.folder" :hint="t.email.folderHint" persistent-hint />
        </v-col>
        <v-col cols="12" sm="6">
          <v-text-field v-model="form.sender" :label="t.email.sender" :hint="t.email.senderHint" persistent-hint />
        </v-col>
        <v-col cols="12" sm="6">
          <v-select v-model="form.interval_minutes" :items="intervals" :label="t.email.every" />
        </v-col>
        <v-col cols="12" sm="6">
          <v-select v-model="form.since_days" :items="sinceOptions" :label="t.email.since" />
        </v-col>
      </v-row>
      <v-switch v-model="form.mark_read" :label="t.email.markRead" color="primary" density="compact" hide-details />
      <v-switch v-model="form.enabled" :label="t.email.enabled" color="primary" density="compact" hide-details />

      <v-alert v-if="testResult" :type="testResult.ok ? 'success' : 'error'" variant="tonal" density="compact" class="mt-3" :text="testResult.text" />

      <div class="text-body-2 text-medium-emphasis mt-3">
        <template v-if="!last">{{ t.email.never }}</template>
        <template v-else-if="last.error">
          <span class="text-error">{{ t.email.failed }}</span> · {{ formatDateTime(last.at) }}: {{ last.error }}
        </template>
        <template v-else>{{ t.email.lastRun(relativeTime(last.at)) }} · {{ resultText(last) }}</template>
      </div>
    </v-card-text>
    <v-card-actions class="px-4 pb-4 flex-wrap ga-2">
      <v-btn variant="tonal" prepend-icon="mdi-connection" :loading="testing" :disabled="!canConnect" @click="test">{{ t.email.test }}</v-btn>
      <v-btn variant="tonal" prepend-icon="mdi-email-sync-outline" :loading="running" :disabled="!canConnect" @click="runNow">{{ t.email.runNow }}</v-btn>
      <v-spacer />
      <v-btn color="primary" variant="flat" :loading="saving" @click="save">{{ t.common.save }}</v-btn>
    </v-card-actions>
  </v-card>
</template>
