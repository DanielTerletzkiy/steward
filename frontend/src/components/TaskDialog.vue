<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { useCatalog } from '@/composables/catalog'
import { attempt, notify } from '@/composables/notify'
import type { Task } from '@/types'

// Edit a one-off task: name, due date, category, who does it, notes.
const open = defineModel<boolean>({ default: false })
const props = defineProps<{ task: Task | null; categories: string[] }>()
const { state } = useCatalog()

const form = ref({ name: '', due_date: null as string | null, category: '', assignee: null as string | null, notes: '' })
const busy = ref(false)
const requiredRule = [(v: string | null) => !!v?.trim() || t.common.required]

watch(open, (v) => {
  const task = props.task
  if (!v || !task) return
  form.value = { name: task.name, due_date: task.due_date, category: task.category, assignee: task.assignee, notes: task.notes ?? '' }
})

async function save() {
  const task = props.task
  const f = form.value
  if (!task || !f.name.trim()) return
  busy.value = true
  const res = await attempt(() =>
    api.updateTask(task.id, {
      name: f.name.trim(),
      due_date: f.due_date || null,
      category: f.category?.trim() || t.tasks.defaultCategory,
      assignee: f.assignee || null,
      notes: f.notes.trim() || null,
    }),
  )
  busy.value = false
  if (res) {
    notify(t.tasks.saved)
    open.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" max-width="520" scrollable>
    <v-card :title="t.tasks.edit" prepend-icon="mdi-pencil">
      <v-card-text>
        <v-form @submit.prevent="save">
          <v-text-field v-model="form.name" :label="t.common.name" :rules="requiredRule" autofocus />
          <v-row dense>
            <v-col cols="12" sm="6"><v-text-field v-model="form.due_date" type="date" :label="t.common.dueDate" clearable /></v-col>
            <v-col cols="12" sm="6"><v-combobox v-model="form.category" :items="categories" :label="t.common.category" /></v-col>
          </v-row>
          <v-select
            v-model="form.assignee"
            :items="state.people"
            item-title="name"
            item-value="id"
            :label="t.tasks.assignee"
            clearable
            :hint="state.people.length ? '' : t.chores.noPeople"
            persistent-hint
          />
          <v-textarea v-model="form.notes" :label="t.common.notes" rows="2" auto-grow class="mt-2" />
          <button type="submit" hidden />
        </v-form>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="open = false">{{ t.common.cancel }}</v-btn>
        <v-btn color="primary" variant="flat" :loading="busy" @click="save">{{ t.common.save }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
