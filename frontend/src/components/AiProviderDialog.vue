<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { t } from '@/i18n'
import type { AiProvider, AiProviderIn, AiSettings } from '@/types'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ provider: AiProvider | null; types: AiSettings['types']; haEntities: string[]; busy?: boolean }>()
const emit = defineEmits<{ save: [AiProviderIn] }>()
const { xs } = useDisplay()

const form = ref({ type: 'anthropic', name: '', model: '', base_url: '', entity_id: null as string | null, api_key: '', clearKey: false })
const showKey = ref(false)

watch(open, (v) => {
  if (!v) return
  const p = props.provider
  showKey.value = false
  form.value = p
    ? { type: p.type, name: p.name, model: p.model ?? '', base_url: p.base_url ?? '', entity_id: p.entity_id, api_key: '', clearKey: false }
    : { type: props.types.find((x) => x.type !== 'home_assistant')?.type ?? 'anthropic', name: '', model: '', base_url: '', entity_id: null, api_key: '', clearKey: false }
})

const meta = computed(() => props.types.find((x) => x.type === form.value.type))
const isHa = computed(() => form.value.type === 'home_assistant')
const needsUrl = computed(() => ['ollama', 'openai_compatible', 'openai'].includes(form.value.type))
const showKeyField = computed(() => !isHa.value)
const keyStored = computed(() => !!props.provider?.api_key_set && props.provider.type === form.value.type)
const typeItems = computed(() => props.types.map((x) => ({ value: x.type, title: x.label })))

function save() {
  const f = form.value
  const body: AiProviderIn = {
    id: props.provider?.id,
    type: f.type,
    name: f.name.trim() || meta.value?.label || f.type,
    model: isHa.value ? null : f.model.trim() || null,
    base_url: needsUrl.value ? f.base_url.trim() || null : null,
    entity_id: isHa.value ? f.entity_id || null : null,
  }
  if (f.api_key.trim()) body.api_key = f.api_key.trim()
  else if (f.clearKey) body.api_key = ''
  emit('save', body)
}
</script>

<template>
  <v-dialog v-model="open" :fullscreen="xs" max-width="520" scrollable>
    <v-card :rounded="xs ? 0 : 'xl'">
      <v-toolbar color="transparent" density="comfortable">
        <v-btn icon="mdi-close" :title="t.common.close" @click="open = false" />
        <v-toolbar-title class="font-weight-medium">{{ provider ? t.settings.editProvider : t.settings.addProvider }}</v-toolbar-title>
      </v-toolbar>
      <v-divider />
      <v-card-text class="pt-4">
        <v-form @submit.prevent="save">
          <v-select v-model="form.type" :items="typeItems" :label="t.settings.type" />
          <v-text-field v-model="form.name" :label="t.common.name" :placeholder="meta?.label" persistent-placeholder />
          <v-select
            v-if="isHa"
            v-model="form.entity_id"
            :items="haEntities"
            :label="t.settings.entity"
            :hint="t.settings.entityHint"
            persistent-hint
            clearable
          />
          <template v-else>
            <v-text-field
              v-model="form.model"
              :label="t.settings.model"
              :placeholder="meta?.model || undefined"
              :hint="meta?.model ? t.settings.defaultValue(meta.model) : undefined"
              persistent-placeholder
              persistent-hint
              class="mb-2"
            />
            <v-text-field
              v-if="needsUrl"
              v-model="form.base_url"
              :label="t.settings.baseUrl"
              :placeholder="meta?.base_url || 'http://…/v1'"
              :hint="meta?.base_url ? t.settings.defaultValue(meta.base_url) : undefined"
              persistent-placeholder
              persistent-hint
              inputmode="url"
              class="mb-2"
            />
            <v-text-field
              v-if="showKeyField"
              v-model="form.api_key"
              :label="t.settings.apiKey"
              :type="showKey ? 'text' : 'password'"
              autocomplete="off"
              :placeholder="keyStored && !form.clearKey ? '••••••••' : undefined"
              :hint="keyStored ? (form.clearKey ? t.settings.keyCleared : t.settings.keyKeep) : undefined"
              persistent-placeholder
              persistent-hint
              :append-inner-icon="showKey ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
              @click:append-inner="showKey = !showKey"
            />
            <v-checkbox v-if="keyStored && !form.api_key" v-model="form.clearKey" :label="t.settings.clearKey" density="compact" hide-details color="error" />
          </template>
          <button type="submit" hidden />
        </v-form>
      </v-card-text>
      <v-divider />
      <v-card-actions class="px-4">
        <v-spacer />
        <v-btn @click="open = false">{{ t.common.cancel }}</v-btn>
        <v-btn color="primary" variant="flat" :loading="busy" @click="save">{{ t.common.save }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
