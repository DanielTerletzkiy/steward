<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { useResource } from '@/composables/resource'
import { attempt, notify } from '@/composables/notify'
import { conditionIcon, conditionLabel, forecastParts } from '@/composables/weather'
import AiProviderDialog from '@/components/AiProviderDialog.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import EmptyState from '@/components/EmptyState.vue'
import EmailImportCard from '@/components/EmailImportCard.vue'
import LocationsCard from '@/components/LocationsCard.vue'
import TerminalsCard from '@/components/TerminalsCard.vue'
import type { AiJob, AiProvider, AiProviderIn, AiSettings, Forecast, WeatherSettings } from '@/types'

const { data: ai, loading: aiLoading, error: aiError, reload: reloadAi } = useResource<AiSettings | null>(() => api.aiSettings(), ['settings'], null)
const { data: wardrobeSettings } = useResource<{ drying_hours: number | null } | null>(() => api.wardrobeSettings(), ['settings', 'wardrobe'], null)
const dryingOptions = [
  { key: 'now', value: 0 },
  { key: 'h12', value: 12 },
  { key: 'h24', value: 24 },
  { key: 'h48', value: 48 },
  { key: 'manual', value: -1 },
]
const dryingValue = computed(() => {
  const h = wardrobeSettings.value?.drying_hours
  return h === undefined ? undefined : h === null ? -1 : h
})
const savingDrying = ref(false)
async function setDrying(v: number) {
  if (v == null || v === dryingValue.value) return
  savingDrying.value = true
  const res = await attempt(() => api.saveWardrobeSettings({ drying_hours: v === -1 ? null : v }))
  savingDrying.value = false
  if (res) {
    wardrobeSettings.value = res
    notify(t.settings.saved)
  }
}

const { data: weather, reload: reloadWeather } = useResource<WeatherSettings | null>(() => api.weatherSettings(), ['settings'], null)

const JOBS: AiJob[] = ['scan', 'wardrobe', 'outfits']
const typeIcon: Record<string, string> = {
  home_assistant: 'mdi-home-assistant', anthropic: 'mdi-creation', openai: 'mdi-robot-outline', ollama: 'mdi-server-outline',
  openai_compatible: 'mdi-server-network', google: 'mdi-google',
}
const typeLabel = (type: string) => ai.value?.types.find((x) => x.type === type)?.label ?? type

// --- AI: every change saves the whole config right away.
const saving = ref(false)
function asInput(p: AiProvider): AiProviderIn {
  return { id: p.id, type: p.type, name: p.name, model: p.model, base_url: p.base_url, entity_id: p.entity_id }
}
async function saveAi(providers: AiProviderIn[], jobs: Record<string, string | null>) {
  saving.value = true
  const res = await attempt(() => api.saveAiSettings({ providers, jobs }))
  saving.value = false
  if (res) {
    ai.value = res
    notify(t.settings.saved)
  }
  return !!res
}
const currentProviders = () => (ai.value?.providers ?? []).map(asInput)
const currentJobs = () => ({ ...(ai.value?.jobs ?? {}) }) as Record<string, string | null>

function jobItems() {
  return [
    { value: '__auto', title: t.settings.automatic },
    ...(ai.value?.providers ?? []).map((p) => ({ value: p.id, title: p.name })),
    { value: 'off', title: t.settings.off },
  ]
}
async function setJob(job: AiJob, value: string) {
  const jobs = currentJobs()
  jobs[job] = value === '__auto' ? null : value
  await saveAi(currentProviders(), jobs)
}
function effectiveText(job: AiJob) {
  if (ai.value?.jobs[job] === 'off') return t.settings.turnedOff
  const e = ai.value?.effective[job]
  if (!e) return t.settings.notAvailable
  return t.settings.uses(e.model ? `${e.name} · ${e.model}` : e.name)
}

const dialog = ref(false)
const editing = ref<AiProvider | null>(null)
function openProvider(p: AiProvider | null) {
  editing.value = p
  dialog.value = true
}
async function saveProvider(body: AiProviderIn) {
  const providers = currentProviders()
  const i = body.id ? providers.findIndex((p) => p.id === body.id) : -1
  if (i >= 0) providers[i] = body
  else providers.push(body)
  if (await saveAi(providers, currentJobs())) dialog.value = false
}
const removing = ref<AiProvider | null>(null)
const confirmRemove = ref(false)
async function removeProvider() {
  const p = removing.value
  if (!p) return
  const jobs = currentJobs()
  for (const j of JOBS) if (jobs[j] === p.id) jobs[j] = null
  await saveAi(currentProviders().filter((x) => x.id !== p.id), jobs)
}

const tests = reactive<Record<string, { busy: boolean; ok?: boolean; text?: string }>>({})
async function test(id: string) {
  tests[id] = { busy: true }
  try {
    const res = await api.testAi(id)
    const answer = res.answer as { greeting?: string } | null
    tests[id] = { busy: false, ok: res.ok, text: answer?.greeting ?? (res.ok ? '' : JSON.stringify(res.answer)) }
  } catch (e) {
    tests[id] = { busy: false, ok: false, text: e instanceof Error ? e.message : String(e) }
  }
}

// --- weather
const weatherForm = ref({ entity_id: null as string | null, latitude: '' as string | number, longitude: '' as string | number })
watch(
  weather,
  (w) => {
    if (w) weatherForm.value = { entity_id: w.entity_id ?? null, latitude: w.latitude ?? '', longitude: w.longitude ?? '' }
  },
  { immediate: true },
)
const num = (v: string | number) => (v === '' || v == null ? null : Number(String(v).replace(',', '.')))
const weatherDirty = computed(() => {
  const w = weather.value
  if (!w) return false
  const f = weatherForm.value
  return (f.entity_id ?? null) !== (w.entity_id ?? null) || num(f.latitude) !== (w.latitude ?? null) || num(f.longitude) !== (w.longitude ?? null)
})
const savingWeather = ref(false)
async function saveWeather() {
  const f = weatherForm.value
  const lat = num(f.latitude)
  const lon = num(f.longitude)
  savingWeather.value = true
  const res = await attempt(() =>
    api.saveWeatherSettings({
      entity_id: f.entity_id || undefined,
      latitude: lat != null && Number.isFinite(lat) ? lat : undefined,
      longitude: lon != null && Number.isFinite(lon) ? lon : undefined,
    }),
  )
  savingWeather.value = false
  if (res !== undefined) {
    notify(t.settings.saved)
    await reloadWeather()
    loadForecast()
  }
}
const locating = ref(false)
function useMyLocation() {
  if (!navigator.geolocation) return notify(t.settings.locationFailed, { color: 'error' })
  locating.value = true
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      locating.value = false
      weatherForm.value.latitude = Math.round(pos.coords.latitude * 1000) / 1000
      weatherForm.value.longitude = Math.round(pos.coords.longitude * 1000) / 1000
    },
    () => {
      locating.value = false
      notify(t.settings.locationFailed, { color: 'error' })
    },
    { timeout: 15000 },
  )
}

const forecast = ref<Forecast | null>(null)
const forecastError = ref<string | null>(null)
const forecastLoading = ref(false)
async function loadForecast() {
  forecastLoading.value = true
  try {
    forecast.value = await api.forecast()
    forecastError.value = null
  } catch (e) {
    forecast.value = null
    forecastError.value = e instanceof Error ? e.message : String(e)
  } finally {
    forecastLoading.value = false
  }
}
loadForecast()
</script>

<template>
  <div class="page" style="max-width: 960px">
    <div class="page-title mb-4">{{ t.settings.title }}</div>

    <v-alert v-if="aiError && !ai" type="error" variant="tonal" :text="aiError" class="mb-4">
      <template #append><v-btn variant="text" @click="reloadAi">{{ t.app.retry }}</v-btn></template>
    </v-alert>
    <v-skeleton-loader v-if="aiLoading && !ai" type="article, list-item-two-line@3" class="rounded-xl mb-4" />

    <template v-if="ai">
      <!-- AI -->
      <div class="d-flex align-center mb-1">
        <v-icon icon="mdi-creation" class="mr-2" color="primary" />
        <div class="text-h6">{{ t.settings.ai }}</div>
        <v-progress-circular v-if="saving" indeterminate size="18" width="2" color="primary" class="ml-3" />
      </div>
      <div class="text-body-2 text-medium-emphasis mb-4" style="max-width: 680px">{{ t.settings.aiIntro }}</div>

      <v-card variant="flat" border class="mb-4">
        <v-list bg-color="transparent" lines="two" class="py-0">
          <template v-for="(job, i) in JOBS" :key="job">
            <v-divider v-if="i > 0" />
            <v-list-item class="py-3">
              <div class="d-flex flex-column flex-sm-row align-sm-center ga-3">
                <div class="flex-grow-1 min-w-0">
                  <div class="text-body-1 font-weight-medium">{{ t.settings.jobs[job] }}</div>
                  <div class="text-body-2 text-medium-emphasis">{{ t.settings.jobHints[job] }}</div>
                </div>
                <div class="job-select">
                  <v-select
                    :model-value="ai.jobs[job] ?? '__auto'"
                    :items="jobItems()"
                    density="compact"
                    hide-details
                    :disabled="saving"
                    @update:model-value="(v: string) => setJob(job, v)"
                  />
                  <div class="text-caption mt-1 d-flex align-center" :class="ai.effective[job] && ai.jobs[job] !== 'off' ? 'text-success' : 'text-medium-emphasis'">
                    <v-icon :icon="ai.effective[job] && ai.jobs[job] !== 'off' ? 'mdi-check-circle-outline' : 'mdi-minus-circle-outline'" size="14" class="mr-1" />
                    <span class="text-truncate">{{ effectiveText(job) }}</span>
                  </div>
                </div>
              </div>
            </v-list-item>
          </template>
        </v-list>
        <v-divider />
        <div class="d-flex align-start pa-4 text-body-2 text-medium-emphasis">
          <v-icon icon="mdi-information-outline" size="18" class="mr-2 mt-px" />{{ t.settings.automaticHint }}
        </div>
      </v-card>

      <!-- Home Assistant AI Task -->
      <v-card variant="flat" border class="mb-4">
        <v-list-item class="py-3">
          <template #prepend><v-avatar color="primary" variant="tonal"><v-icon icon="mdi-home-assistant" /></v-avatar></template>
          <v-list-item-title class="font-weight-medium">{{ t.settings.haTask }}</v-list-item-title>
          <v-list-item-subtitle>
            <template v-if="!ai.home_assistant.connected">{{ t.settings.haOffline }}</template>
            <template v-else-if="!ai.home_assistant.ai_task">{{ t.settings.haNoTask }}</template>
            <template v-else>{{ t.settings.haAvailable }} · {{ ai.home_assistant.ai_task_entities.join(', ') }}</template>
          </v-list-item-subtitle>
          <template v-if="ai.home_assistant.ai_task" #append>
            <v-btn variant="tonal" size="small" :loading="tests.ha?.busy" @click="test('ha')">{{ t.settings.test }}</v-btn>
          </template>
        </v-list-item>
        <div v-if="tests.ha && !tests.ha.busy" class="px-4 pb-3">
          <v-alert :type="tests.ha.ok ? 'success' : 'error'" variant="tonal" density="compact" :title="tests.ha.ok ? t.settings.testOk : t.settings.testFailed" :text="tests.ha.text || undefined" />
        </div>
      </v-card>

      <!-- Providers -->
      <div class="d-flex align-center mb-2">
        <div class="text-subtitle-1 font-weight-medium">{{ t.settings.providers }}</div>
        <v-spacer />
        <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-plus" @click="openProvider(null)">{{ t.settings.addProvider }}</v-btn>
      </div>
      <v-card v-if="!ai.providers.length" variant="flat" border class="mb-6">
        <EmptyState compact icon="mdi-robot-outline" :title="t.settings.noProviders" :text="t.settings.noProvidersHint" />
      </v-card>
      <v-row v-else dense class="mb-6">
        <v-col v-for="p in ai.providers" :key="p.id" cols="12" sm="6">
          <v-card variant="flat" border class="h-100 d-flex flex-column">
            <v-card-item>
              <template #prepend><v-avatar color="secondary" variant="tonal"><v-icon :icon="typeIcon[p.type] ?? 'mdi-robot-outline'" /></v-avatar></template>
              <v-card-title class="text-subtitle-1 font-weight-medium">{{ p.name }}</v-card-title>
              <v-card-subtitle>{{ typeLabel(p.type) }}<template v-if="p.model"> · {{ p.model }}</template></v-card-subtitle>
              <template #append>
                <v-menu location="bottom end">
                  <template #activator="{ props: menuProps }"><v-btn v-bind="menuProps" icon="mdi-dots-vertical" variant="text" size="small" /></template>
                  <v-list density="compact">
                    <v-list-item prepend-icon="mdi-pencil-outline" :title="t.common.edit" @click="openProvider(p)" />
                    <v-list-item prepend-icon="mdi-delete-outline" base-color="error" :title="t.settings.removeProvider" @click="removing = p; confirmRemove = true" />
                  </v-list>
                </v-menu>
              </template>
            </v-card-item>
            <v-card-text class="pt-0 d-flex flex-wrap ga-1">
              <v-chip v-if="p.base_url" variant="outlined" label prepend-icon="mdi-link-variant" class="text-truncate" style="max-width: 100%">{{ p.base_url }}</v-chip>
              <v-chip v-if="p.entity_id" variant="outlined" label prepend-icon="mdi-home-assistant">{{ p.entity_id }}</v-chip>
              <v-chip
                v-if="p.type !== 'home_assistant'"
                :color="p.api_key_set ? 'success' : ai.types.find((x) => x.type === p.type)?.key ? 'warning' : undefined"
                variant="tonal"
                label
                :prepend-icon="p.api_key_set ? 'mdi-key-outline' : 'mdi-key-remove'"
              >
                {{ p.api_key_set ? t.settings.keySet : t.settings.noKey }}
              </v-chip>
            </v-card-text>
            <v-spacer />
            <div v-if="tests[p.id] && !tests[p.id].busy" class="px-4">
              <v-alert :type="tests[p.id].ok ? 'success' : 'error'" variant="tonal" density="compact" :title="tests[p.id].ok ? t.settings.testOk : t.settings.testFailed" :text="tests[p.id].text || undefined" class="text-break" />
            </div>
            <v-card-actions class="px-4">
              <v-btn variant="tonal" size="small" prepend-icon="mdi-connection" :loading="tests[p.id]?.busy" @click="test(p.id)">{{ t.settings.test }}</v-btn>
              <v-btn variant="text" size="small" @click="openProvider(p)">{{ t.common.edit }}</v-btn>
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>
    </template>

    <!-- Wardrobe -->
    <!-- Storage locations -->
    <div class="d-flex align-center mb-1">
      <v-icon icon="mdi-fridge-outline" class="mr-2" color="primary" />
      <div class="text-h6">{{ t.locations.title }}</div>
    </div>
    <div class="text-body-2 text-medium-emphasis mb-4" style="max-width: 680px">{{ t.locations.intro }}</div>
    <LocationsCard />

    <!-- Kitchen terminals -->
    <div class="d-flex align-center mb-1">
      <v-icon icon="mdi-monitor-dashboard" class="mr-2" color="primary" />
      <div class="text-h6">{{ t.terminals.title }}</div>
    </div>
    <div class="text-body-2 text-medium-emphasis mb-4" style="max-width: 680px">{{ t.terminals.intro }}</div>
    <TerminalsCard />

    <!-- Receipts from email -->
    <div class="d-flex align-center mb-1">
      <v-icon icon="mdi-email-arrow-left-outline" class="mr-2" color="primary" />
      <div class="text-h6">{{ t.email.title }}</div>
    </div>
    <div class="text-body-2 text-medium-emphasis mb-4" style="max-width: 680px">{{ t.email.intro }}</div>
    <EmailImportCard />

    <div class="d-flex align-center mb-1">
      <v-icon icon="mdi-hanger" class="mr-2" color="primary" />
      <div class="text-h6">{{ t.settings.wardrobe }}</div>
      <v-progress-circular v-if="savingDrying" indeterminate size="18" width="2" color="primary" class="ml-3" />
    </div>
    <v-card variant="flat" border class="mb-6">
      <v-card-text>
        <div class="text-subtitle-2">{{ t.settings.dryingTime }}</div>
        <div class="text-body-2 text-medium-emphasis mb-2">{{ t.settings.dryingHint }}</div>
        <v-chip-group :model-value="dryingValue" mandatory column selected-class="text-primary" @update:model-value="setDrying">
          <v-chip v-for="o in dryingOptions" :key="o.key" :value="o.value" variant="outlined" size="default" filter :disabled="savingDrying">
            {{ t.settings.dryingOptions[o.key] }}
          </v-chip>
        </v-chip-group>
      </v-card-text>
    </v-card>

    <!-- Weather -->
    <div class="d-flex align-center mb-1">
      <v-icon icon="mdi-weather-partly-cloudy" class="mr-2" color="primary" />
      <div class="text-h6">{{ t.settings.weather }}</div>
    </div>
    <div class="text-body-2 text-medium-emphasis mb-4">{{ t.settings.weatherIntro }}</div>
    <v-row>
      <v-col cols="12" md="7">
        <v-card variant="flat" border class="h-100">
          <v-card-text>
            <v-select
              v-if="weather?.home_assistant.connected && weather.home_assistant.entities.length"
              v-model="weatherForm.entity_id"
              :items="weather.home_assistant.entities"
              :label="t.settings.weatherEntity"
              :hint="t.settings.weatherEntityHint"
              persistent-hint
              clearable
              prepend-inner-icon="mdi-home-assistant"
              class="mb-4"
            />
            <div class="text-subtitle-2 mb-1">{{ t.settings.location }}</div>
            <div class="text-caption text-medium-emphasis mb-3">{{ t.settings.locationHint }}</div>
            <v-row dense>
              <v-col cols="6"><v-text-field v-model="weatherForm.latitude" :label="t.settings.latitude" inputmode="decimal" /></v-col>
              <v-col cols="6"><v-text-field v-model="weatherForm.longitude" :label="t.settings.longitude" inputmode="decimal" /></v-col>
            </v-row>
            <div class="d-flex flex-wrap ga-2">
              <v-btn variant="tonal" size="small" prepend-icon="mdi-crosshairs-gps" :loading="locating" @click="useMyLocation">{{ t.settings.useMyLocation }}</v-btn>
              <v-spacer />
              <v-btn color="primary" variant="flat" :disabled="!weatherDirty" :loading="savingWeather" @click="saveWeather">{{ t.common.save }}</v-btn>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="5">
        <v-card variant="tonal" color="primary" class="h-100">
          <v-card-item>
            <v-card-title class="text-subtitle-1 font-weight-bold">{{ t.settings.forecast }}</v-card-title>
            <template #append><v-btn icon="mdi-refresh" variant="text" size="small" :loading="forecastLoading" :title="t.app.retry" @click="loadForecast" /></template>
          </v-card-item>
          <v-card-text v-if="forecast" class="text-high-emphasis">
            <div class="d-flex align-center mb-2">
              <v-icon :icon="conditionIcon(forecast.conditions[0])" size="40" class="mr-3" />
              <div>
                <div class="text-h5 font-weight-bold text-tabular">{{ Math.round(forecast.temp_min) }}–{{ Math.round(forecast.temp_max) }} °C</div>
                <div class="text-body-2">{{ forecast.conditions.map(conditionLabel).join(', ') }}</div>
              </div>
            </div>
            <div class="text-body-2">{{ forecastParts(forecast).slice(1).join(' · ') }}</div>
            <div class="text-caption opacity-80 mt-2">{{ t.settings.source(t.settings.sources[forecast.source] ?? forecast.source) }}</div>
          </v-card-text>
          <v-card-text v-else-if="forecastError" class="text-high-emphasis">
            <div class="d-flex align-start"><v-icon icon="mdi-weather-cloudy-alert" class="mr-2" />
              <div><div class="font-weight-medium">{{ t.settings.forecastUnavailable }}</div><div class="text-body-2 opacity-80">{{ forecastError }}</div></div>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <AiProviderDialog v-if="ai" v-model="dialog" :provider="editing" :types="ai.types" :ha-entities="ai.home_assistant.ai_task_entities" :busy="saving" @save="saveProvider" />
    <ConfirmDialog v-model="confirmRemove" :title="t.settings.removeProvider" :text="t.settings.confirmRemove(removing?.name ?? '')" :confirm-label="t.common.delete" @confirm="removeProvider" />
  </div>
</template>

<style scoped>
.job-select {
  width: 100%;
  max-width: 280px;
}
@media (max-width: 599px) {
  .job-select {
    max-width: none;
  }
}
</style>
