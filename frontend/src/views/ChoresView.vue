<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDisplay } from 'vuetify'
import { api } from '@/api'
import { LOCALE, t } from '@/i18n'
import { useResource } from '@/composables/resource'
import { useCatalog } from '@/composables/catalog'
import { attempt, notify } from '@/composables/notify'
import { describeSchedule, mdiIcon, parseDateTime, parseDay, relativeDue, relativePast, daysFromToday } from '@/composables/format'
import EmptyState from '@/components/EmptyState.vue'
import StatusChip from '@/components/StatusChip.vue'
import ChoreDialog from '@/components/ChoreDialog.vue'
import TaskDialog from '@/components/TaskDialog.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import type { Chore, Task } from '@/types'

const { smAndUp } = useDisplay()
const { state, personName } = useCatalog()
const { data: chores, loading: choresLoading, error: choresError } = useResource<Chore[]>(() => api.chores(), ['chores', 'people'], [])
const { data: tasks, loading: tasksLoading } = useResource<Task[]>(() => api.tasks(true), ['tasks'], [])

const choreDialog = ref(false)
const editing = ref<Chore | null>(null)
function openChore(c: Chore | null) {
  editing.value = c
  choreDialog.value = true
}
const deleteChore = ref<Chore | null>(null)
const confirmOpen = ref(false)

const statusColor: Record<string, string> = { overdue: 'error', due_today: 'warning', due_soon: 'info', scheduled: 'success', manual: 'grey' }

function dueText(c: Chore) {
  if (!c.next_due) return t.status.manual
  return relativeDue(parseDateTime(c.next_due))
}

async function execute(c: Chore, skipped = false, personId?: string | null) {
  const res = await attempt(() => api.executeChore(c.id, { skipped, person_id: personId ?? c.next_assignee ?? null }))
  if (res) notify(skipped ? t.chores.skippedMsg(c.name) : t.chores.doneMsg(c.name))
}
async function removeChore() {
  const c = deleteChore.value
  if (!c) return
  await attempt(() => api.deleteChore(c.id))
}

// --- tasks
const showDone = ref(false)
const openTasks = computed(() =>
  tasks.value
    .filter((x) => !x.done_at)
    .sort((a, b) => (a.due_date ?? '9999').localeCompare(b.due_date ?? '9999') || a.name.localeCompare(b.name, LOCALE)),
)
const doneTasks = computed(() => tasks.value.filter((x) => x.done_at).sort((a, b) => (b.done_at ?? '').localeCompare(a.done_at ?? '')))
const newTask = ref('')
const newDue = ref<string | null>(null)
const newCategory = ref<string | null>(null)
const taskCategories = computed(() => [...new Set([t.tasks.defaultCategory, ...tasks.value.map((x) => x.category)])].sort())

async function addTask() {
  const name = newTask.value.trim()
  if (!name) return
  const res = await attempt(() => api.createTask({ name, due_date: newDue.value || null, category: newCategory.value || t.tasks.defaultCategory }))
  if (res) {
    newTask.value = ''
    newDue.value = null
  }
}
async function setDone(task: Task, done: boolean) {
  const res = await attempt(() => api.updateTask(task.id, { done }))
  if (res && done)
    notify(t.tasks.doneMsg(task.name), { action: { label: t.common.undo, run: () => void attempt(() => api.updateTask(task.id, { done: false })) } })
}
const taskDialog = ref(false)
const editingTask = ref<Task | null>(null)
function openTask(task: Task) {
  editingTask.value = task
  taskDialog.value = true
}
async function removeTask(task: Task) {
  const ok = await attempt(async () => (await api.deleteTask(task.id), true))
  if (ok) notify(t.tasks.deleted)
}
function taskDueColor(task: Task) {
  if (!task.due_date) return undefined
  const n = daysFromToday(parseDay(task.due_date))
  return n < 0 ? 'error' : n === 0 ? 'warning' : n <= 3 ? 'info' : undefined
}
</script>

<template>
  <div class="page">
    <v-row>
      <!-- Chores -->
      <v-col cols="12" lg="7">
        <div class="d-flex align-center mb-4">
          <div class="page-title">{{ t.chores.title }}</div>
          <v-spacer />
          <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openChore(null)">{{ smAndUp ? t.chores.newChore : t.common.create }}</v-btn>
        </div>
        <v-alert v-if="choresError" type="error" variant="tonal" :text="choresError" class="mb-3" />
        <v-skeleton-loader v-if="choresLoading && !chores.length" type="list-item-two-line@4" class="rounded-xl" />
        <EmptyState v-else-if="!chores.length" icon="mdi-broom" :title="t.chores.empty" :text="t.chores.emptyHint">
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="openChore(null)">{{ t.chores.newChore }}</v-btn>
        </EmptyState>
        <v-card v-else variant="flat" border>
          <v-list lines="three" bg-color="transparent">
            <template v-for="(c, idx) in chores" :key="c.id">
              <v-divider v-if="idx > 0" inset />
              <v-list-item class="py-3">
                <template #prepend>
                  <v-avatar :color="statusColor[c.status]" variant="tonal"><v-icon :icon="mdiIcon(c.icon)" /></v-avatar>
                </template>
                <v-list-item-title class="font-weight-medium wrap clickable" @click="openChore(c)">{{ c.name }}</v-list-item-title>
                <div class="text-body-2 mt-1" :class="c.status === 'overdue' ? 'text-error' : c.status === 'due_today' ? 'text-warning' : 'text-medium-emphasis'">
                  <v-icon icon="mdi-calendar" size="14" class="mr-1" />{{ dueText(c) }}
                </div>
                <div class="d-flex flex-wrap align-center ga-1 mt-1">
                  <v-chip variant="tonal" prepend-icon="mdi-calendar-sync">{{ describeSchedule(c) }}</v-chip>
                  <v-chip variant="tonal" prepend-icon="mdi-account-outline">{{ personName(c.next_assignee) ?? t.chores.everyone }}</v-chip>
                  <StatusChip v-if="smAndUp" :status="c.status" kind="chore" />
                </div>
                <div v-if="c.last_done" class="text-caption text-medium-emphasis mt-1">
                  {{ t.chores.lastDone }}: {{ relativePast(c.last_done) }}<template v-if="c.last_done_by"> · {{ personName(c.last_done_by) }}</template>
                </div>
                <template #append>
                  <div class="d-flex flex-column flex-sm-row align-end align-sm-center ga-1">
                    <v-btn color="primary" :variant="c.status === 'overdue' || c.status === 'due_today' ? 'flat' : 'tonal'" size="small" prepend-icon="mdi-check" @click="execute(c)">
                      {{ t.common.done }}
                    </v-btn>
                    <v-menu location="bottom end">
                      <template #activator="{ props }"><v-btn v-bind="props" icon="mdi-dots-vertical" variant="text" size="small" /></template>
                      <v-list density="compact">
                        <v-list-item prepend-icon="mdi-debug-step-over" :title="t.common.skip" :disabled="c.schedule === 'manual'" @click="execute(c, true)" />
                        <v-list-item v-for="p in state.people" :key="p.id" prepend-icon="mdi-account-check-outline" :title="`${t.common.done}: ${p.name}`" @click="execute(c, false, p.id)" />
                        <v-divider />
                        <v-list-item prepend-icon="mdi-pencil-outline" :title="t.common.edit" @click="openChore(c)" />
                        <v-list-item prepend-icon="mdi-delete-outline" base-color="error" :title="t.common.delete" @click="deleteChore = c; confirmOpen = true" />
                      </v-list>
                    </v-menu>
                  </div>
                </template>
              </v-list-item>
            </template>
          </v-list>
        </v-card>
      </v-col>

      <!-- Tasks -->
      <v-col cols="12" lg="5">
        <div class="d-flex align-center mb-4" style="min-height: 36px">
          <div class="page-title">{{ t.chores.tasksTitle }}</div>
          <v-spacer />
          <v-btn variant="text" size="small" :prepend-icon="showDone ? 'mdi-eye-off-outline' : 'mdi-eye-outline'" @click="showDone = !showDone">{{ t.tasks.showDone }}</v-btn>
        </div>
        <v-card variant="flat" border>
          <v-form class="pa-3 pb-0" @submit.prevent="addTask">
            <v-text-field v-model="newTask" :placeholder="t.tasks.addPlaceholder" prepend-inner-icon="mdi-plus" hide-details density="compact" class="mb-2" @keydown.enter.prevent="addTask">
              <template #append-inner>
                <v-btn v-if="newTask.trim()" icon="mdi-arrow-right" color="primary" variant="flat" size="x-small" @mousedown.stop @click.stop="addTask" />
              </template>
            </v-text-field>
            <v-expand-transition>
              <v-row v-if="newTask.trim()" dense>
                <v-col cols="6"><v-text-field v-model="newDue" type="date" :label="t.common.dueDate" density="compact" hide-details clearable /></v-col>
                <v-col cols="6"><v-combobox v-model="newCategory" :items="taskCategories" :label="t.common.category" density="compact" hide-details /></v-col>
              </v-row>
            </v-expand-transition>
          </v-form>
          <v-skeleton-loader v-if="tasksLoading && !tasks.length" type="list-item@3" />
          <EmptyState v-else-if="!openTasks.length" compact icon="mdi-check-decagram-outline" :title="t.tasks.empty" :text="t.tasks.emptyHint" />
          <v-list v-else bg-color="transparent" lines="two">
            <v-list-item v-for="task in openTasks" :key="task.id">
              <template #prepend><v-checkbox-btn color="primary" :model-value="false" @update:model-value="setDone(task, true)" /></template>
              <v-list-item-title class="wrap clickable" @click="openTask(task)">{{ task.name }}</v-list-item-title>
              <div class="d-flex flex-wrap ga-1 mt-1">
                <v-chip v-if="task.due_date" :color="taskDueColor(task)" variant="tonal" prepend-icon="mdi-calendar" label>{{ relativeDue(parseDay(task.due_date)) }}</v-chip>
                <v-chip variant="outlined" label>{{ task.category }}</v-chip>
                <v-chip v-if="task.assignee" variant="outlined" prepend-icon="mdi-account-outline" label>{{ personName(task.assignee) }}</v-chip>
              </div>
              <div v-if="task.notes" class="text-caption text-medium-emphasis mt-1">{{ task.notes }}</div>
              <template #append>
                <v-btn icon="mdi-pencil-outline" variant="text" size="small" :title="t.common.edit" @click="openTask(task)" />
                <v-btn icon="mdi-delete-outline" variant="text" size="small" :title="t.common.delete" @click="removeTask(task)" />
              </template>
            </v-list-item>
          </v-list>
          <template v-if="showDone && doneTasks.length">
            <v-divider />
            <v-list bg-color="transparent" density="compact">
              <v-list-item v-for="task in doneTasks" :key="task.id">
                <template #prepend><v-checkbox-btn color="primary" :model-value="true" @update:model-value="setDone(task, false)" /></template>
                <v-list-item-title class="line-through text-medium-emphasis wrap">{{ task.name }}</v-list-item-title>
                <template #append><v-btn icon="mdi-delete-outline" variant="text" size="small" @click="removeTask(task)" /></template>
              </v-list-item>
            </v-list>
          </template>
        </v-card>
      </v-col>
    </v-row>

    <ChoreDialog v-model="choreDialog" :chore="editing" />
    <TaskDialog v-model="taskDialog" :task="editingTask" :categories="taskCategories" />
    <ConfirmDialog v-model="confirmOpen" :title="t.chores.deleteChore" :text="t.chores.confirmDelete(deleteChore?.name ?? '')" @confirm="removeChore" />
  </div>
</template>
