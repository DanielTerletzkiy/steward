<script setup lang="ts">
import { t } from '@/i18n'
import type { AiProblem } from '@/composables/aiErrors'

defineProps<{ problem: AiProblem }>()
const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <v-alert
    :type="problem.kind === 'setup' ? 'info' : 'error'"
    variant="tonal"
    density="compact"
    :icon="problem.kind === 'setup' ? 'mdi-creation' : undefined"
    :title="problem.kind === 'setup' ? t.ai.notSetUp : problem.kind === 'failed' ? t.ai.failed : undefined"
    closable
    @click:close="emit('close')"
  >
    <div class="text-body-2">{{ problem.kind === 'setup' ? t.ai.notSetUpHint : problem.message }}</div>
    <v-btn v-if="problem.kind === 'setup'" to="/settings" size="small" variant="tonal" class="mt-2" prepend-icon="mdi-cog-outline">{{ t.ai.openSettings }}</v-btn>
  </v-alert>
</template>
