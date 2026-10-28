<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { describeSchedule, todayIso } from '@/composables/format'
import { useCatalog } from '@/composables/catalog'
import { attempt, notify } from '@/composables/notify'
import type { Assignment, ChoreIn, Schedule } from '@/types'

const open = defineModel<boolean>({ default: false })
const { state } = useCatalog()

const blank = () => ({
  name: '',
  description: '',
  icon: '',
  schedule: 'weekly' as Schedule,
  interval: 1,
  weekdays: [] as number[],
  assignment: 'none' as Assignment,
  assignees: [] as string[],
  firstDue: todayIso(),
})
const form = ref(blank())
const busy = ref(false)
const requiredRule = [(v: string | null) => !!v?.trim() || t.common.required]
watch(open, (v) => v && (form.value = blank()))

const schedules = (Object.keys(t.chores.schedules) as Schedule[]).map((value) => ({ value, title: t.chores.schedules[value] }))
const assignments = (Object.keys(t.chores.assignments) as Assignment[]).map((value) => ({ value, title: t.chores.assignments[value] }))
const preview = computed(() => describeSchedule(form.value))

async function save() {
  const f = form.value
  if (!f.name.trim()) return
  busy.value = true
  const body: ChoreIn = {
    name: f.name.trim(),
    description: f.description || null,
    icon: f.icon ? (f.icon.startsWith('mdi:') ? f.icon : `mdi:${f.icon.replace(/^mdi-/, '')}`) : null,
    schedule: f.schedule,
    interval: Math.max(1, Number(f.interval) || 1),
    weekdays: f.schedule === 'weekly' ? [...f.weekdays].sort() : [],
    assignment: f.assignment,
    assignees: f.assignment === 'none' ? [] : f.assignees,
    // Midnight local time of the chosen day.
    first_due: f.schedule !== 'manual' && f.firstDue ? new Date(`${f.firstDue}T00:00:00`).toISOString() : null,
  }
  const res = await attempt(() => api.createChore(body))
  busy.value = false
  if (res) {
    notify(t.chores.created)
    open.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" max-width="600" scrollable>
    <v-card :title="t.chores.newChore" prepend-icon="mdi-broom">
      <v-card-text>
        <v-form @submit.prevent="save">
          <v-text-field v-model="form.name" :label="t.common.name" autofocus :rules="requiredRule" />
          <v-select v-model="form.schedule" :label="t.chores.schedule" :items="schedules" />
          <v-text-field
            v-if="form.schedule !== 'manual'"
            v-model.number="form.interval"
            :label="t.chores.interval"
            type="number"
            min="1"
            :prefix="form.schedule === 'dynamic' ? '' : 'alle'"
            :suffix="t.chores.intervalSuffix[form.schedule]"
          />
          <div v-if="form.schedule === 'weekly'" class="mb-4">
            <div class="text-caption text-medium-emphasis mb-1">{{ t.chores.weekdays }}</div>
            <v-chip-group v-model="form.weekdays" multiple column selected-class="text-primary" filter>
              <v-chip v-for="(d, i) in t.chores.weekdayShort" :key="i" :value="i" variant="outlined" size="default">{{ d }}</v-chip>
            </v-chip-group>
          </div>
          <v-text-field v-if="form.schedule !== 'manual'" v-model="form.firstDue" :label="t.chores.firstDue" type="date" />
          <v-alert type="info" variant="tonal" density="compact" icon="mdi-calendar-sync" class="mb-4">{{ preview }}</v-alert>
          <v-select v-model="form.assignment" :label="t.chores.assignment" :items="assignments" />
          <v-select
            v-if="form.assignment !== 'none'"
            v-model="form.assignees"
            :label="t.chores.assignees"
            :items="state.people"
            item-title="name"
            item-value="id"
            multiple
            chips
            closable-chips
            :hint="state.people.length ? t.chores.assigneesHint : t.chores.noPeople"
            persistent-hint
            class="mb-2"
          />
          <v-text-field v-model="form.icon" :label="t.chores.icon" placeholder="mdi:broom" :prepend-inner-icon="form.icon ? form.icon.replace(/^mdi:/, 'mdi-') : 'mdi-emoticon-outline'" />
          <v-textarea v-model="form.description" :label="t.chores.description" rows="2" auto-grow />
          <button type="submit" hidden />
        </v-form>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="open = false">{{ t.common.cancel }}</v-btn>
        <v-btn color="primary" variant="flat" :loading="busy" @click="save">{{ t.common.create }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
