<script setup lang="ts">
defineProps<{ icon: string; title: string; text?: string; compact?: boolean }>()
</script>

<template>
  <div class="d-flex flex-column align-center text-center" :class="compact ? 'py-4 px-2' : 'py-12 px-4'">
    <v-avatar :size="compact ? 48 : 80" color="primary" variant="tonal" class="mb-3">
      <v-icon :icon="icon" :size="compact ? 24 : 40" />
    </v-avatar>
    <div :class="compact ? 'text-body-1' : 'text-h6'">{{ title }}</div>
    <div v-if="text" class="text-body-2 text-medium-emphasis mt-1" style="max-width: 420px">{{ text }}</div>
    <div v-if="$slots.default" class="mt-4"><slot /></div>
  </div>
</template>
