<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { api } from '@/api'
import { LANG, t } from '@/i18n'
import { attempt, notify } from '@/composables/notify'
import { todayIso } from '@/composables/format'
import { label, sourceIcon, useVocabulary } from '@/composables/wardrobe'
import { aiProblem, type AiProblem } from '@/composables/aiErrors'
import { asForecast, conditionIcon, forecastParts } from '@/composables/weather'
import OutfitCollage from './OutfitCollage.vue'
import AiProblemAlert from './AiProblemAlert.vue'
import type { Garment, Outfit } from '@/types'

// Today's outfit, plus "Suggest an outfit" (AI when set up, rules otherwise).
const props = defineProps<{ outfits: Outfit[]; garments: Map<number, Garment>; owner: string | null }>()
const emit = defineEmits<{ changed: [] }>()
const { xs } = useDisplay()
const vocab = useVocabulary()

const STORE = 'steward.wardrobe.occasion'
function initialOccasion() {
  try {
    return localStorage.getItem(STORE) || 'comfort'
  } catch {
    return 'comfort'
  }
}
const occasion = ref(initialOccasion())
watch(occasion, (v) => {
  try {
    localStorage.setItem(STORE, v)
  } catch {
    /* storage unavailable */
  }
})
const occasions = computed(() => (vocab.value?.uses ?? ['home', 'comfort', 'going_out', 'work', 'sport', 'formal']).map((u) => ({ value: u, title: label.use(u) })))

const today = computed(() => props.outfits.filter((o) => o.day === todayIso()))
const worn = computed(() => today.value.find((o) => o.worn) ?? null)
const planned = computed(() => today.value.find((o) => !o.worn && o.source === 'manual') ?? null)
const main = computed(() => worn.value ?? planned.value)
const suggestions = computed(() =>
  today.value
    .filter((o) => !o.worn && o.source !== 'manual')
    .sort((a, b) => b.id - a.id)
    .slice(0, 3),
)
const weather = computed(() => asForecast(suggestions.value[0]?.weather ?? main.value?.weather ?? null))

const busy = ref(false)
const problem = ref<AiProblem | null>(null)
async function suggest() {
  busy.value = true
  problem.value = null
  try {
    await api.suggestOutfits({ owner: props.owner, occasion: occasion.value, count: 3, lang: LANG })
    emit('changed')
  } catch (e) {
    problem.value = aiProblem(e)
  } finally {
    busy.value = false
  }
}
async function wear(o: Outfit) {
  const res = await attempt(() => api.wearOutfit(o.id))
  if (res) {
    notify(t.wardrobe.outfitWorn)
    emit('changed')
  }
}
async function rate(o: Outfit, rating: -1 | 1) {
  const res = await attempt(() => api.outfitFeedback(o.id, o.rating === rating ? 0 : rating, o.feedback))
  if (res) emit('changed')
}
</script>

<template>
  <v-card variant="tonal" color="primary" class="h-100">
    <v-card-item prepend-icon="mdi-hanger">
      <v-card-title class="text-subtitle-1 font-weight-bold">{{ t.wardrobe.today }}</v-card-title>
      <v-card-subtitle v-if="weather" class="opacity-90 text-wrap">
        <v-icon :icon="conditionIcon(weather.conditions[0])" size="16" class="mr-1" />{{ forecastParts(weather).join(' · ') }}
      </v-card-subtitle>
      <template v-if="!xs" #append>
        <div class="d-flex align-center ga-2">
          <v-select v-model="occasion" :items="occasions" density="compact" hide-details variant="outlined" style="width: 170px" :disabled="busy" />
          <v-btn color="primary" variant="flat" prepend-icon="mdi-creation" :loading="busy" @click="suggest">
            {{ suggestions.length ? t.wardrobe.anotherOne : t.wardrobe.suggest }}
          </v-btn>
        </div>
      </template>
    </v-card-item>

    <v-card-text class="pt-0 text-high-emphasis">
      <!-- What is worn (or planned) today -->
      <div v-if="main" class="d-flex flex-column flex-sm-row ga-3 mb-3">
        <OutfitCollage :ids="main.garment_ids" :garments="garments" row :max="5" :tile="80" />
        <div class="min-w-0">
          <div class="d-flex flex-wrap ga-1 mb-1">
            <v-chip v-if="main.worn" color="success" variant="flat" prepend-icon="mdi-check" label>{{ t.wardrobe.worn }}</v-chip>
            <v-chip variant="outlined" label :prepend-icon="sourceIcon[main.source] ?? 'mdi-hanger'">{{ label.source(main.source) }}</v-chip>
            <v-chip v-if="main.occasion" variant="outlined" label>{{ label.use(main.occasion) }}</v-chip>
          </div>
          <div v-if="main.reason" class="text-body-2">{{ main.reason }}</div>
          <v-btn v-if="!main.worn" color="primary" variant="flat" size="small" class="mt-2" prepend-icon="mdi-tshirt-crew" @click="wear(main)">{{ t.wardrobe.wear }}</v-btn>
        </div>
      </div>
      <div v-else-if="!suggestions.length && !busy" class="mb-3">
        <div class="text-body-1">{{ t.wardrobe.todayEmpty }}</div>
        <div class="text-body-2 opacity-80">{{ t.wardrobe.todayEmptyHint }}</div>
      </div>

      <div v-if="xs" class="d-flex align-center ga-2 mb-3">
        <v-select v-model="occasion" :items="occasions" density="compact" hide-details variant="outlined" class="flex-grow-1" :disabled="busy" />
        <v-btn color="primary" variant="flat" prepend-icon="mdi-creation" :loading="busy" @click="suggest">
          {{ suggestions.length ? t.wardrobe.anotherOne : t.wardrobe.suggest }}
        </v-btn>
      </div>

      <v-expand-transition>
        <div v-if="busy" class="mb-3">
          <v-progress-linear indeterminate color="primary" rounded class="mb-2" />
          <div class="text-body-2">{{ t.wardrobe.suggesting }}</div>
          <div class="text-caption opacity-80">{{ t.wardrobe.suggestingHint }}</div>
        </div>
      </v-expand-transition>

      <AiProblemAlert v-if="problem" :problem="problem" class="mb-3" @close="problem = null" />

      <template v-if="suggestions.length">
        <div class="text-caption font-weight-medium text-uppercase opacity-80 mb-2">{{ t.wardrobe.suggestions }}</div>
        <v-row dense>
          <v-col v-for="o in suggestions" :key="o.id" cols="12" sm="6" lg="4">
            <v-sheet color="surface" rounded="lg" class="pa-3 h-100 d-flex flex-column suggestion" :class="{ 'opacity-60': busy }">
              <div class="d-flex align-start ga-2 mb-2">
                <OutfitCollage :ids="o.garment_ids" :garments="garments" row :max="4" :tile="56" class="flex-grow-1" />
                <v-chip size="x-small" :color="o.source === 'ai' ? 'primary' : undefined" variant="tonal" label :prepend-icon="o.source === 'ai' ? 'mdi-creation' : 'mdi-lightbulb-outline'" class="flex-shrink-0">
                  {{ o.source === 'ai' ? t.ai.badgeAi : t.ai.badgeRules }}
                </v-chip>
              </div>
              <div v-if="o.reason" class="text-body-2 text-medium-emphasis reason">{{ o.reason }}</div>
              <v-spacer />
              <div class="d-flex align-center mt-2">
                <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-tshirt-crew" :disabled="busy" @click="wear(o)">{{ t.wardrobe.wear }}</v-btn>
                <v-spacer />
                <v-btn :icon="o.rating === 1 ? 'mdi-thumb-up' : 'mdi-thumb-up-outline'" :color="o.rating === 1 ? 'success' : undefined" size="small" variant="text" :title="t.wardrobe.liked" @click="rate(o, 1)" />
                <v-btn :icon="o.rating === -1 ? 'mdi-thumb-down' : 'mdi-thumb-down-outline'" :color="o.rating === -1 ? 'error' : undefined" size="small" variant="text" :title="t.wardrobe.disliked" @click="rate(o, -1)" />
              </div>
            </v-sheet>
          </v-col>
        </v-row>
      </template>
    </v-card-text>
  </v-card>
</template>

<style scoped>
.reason {
  display: -webkit-box;
  -webkit-line-clamp: 4;
  line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
