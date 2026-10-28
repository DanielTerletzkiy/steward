<script setup lang="ts">
import { t } from '@/i18n'

const open = defineModel<boolean>({ default: false })
defineProps<{ title: string; text: string; confirmLabel?: string; color?: string }>()
const emit = defineEmits<{ confirm: [] }>()
</script>

<template>
  <v-dialog v-model="open" max-width="420">
    <v-card :title="title" :text="text">
      <v-card-actions>
        <v-spacer />
        <v-btn @click="open = false">{{ t.common.cancel }}</v-btn>
        <v-btn :color="color ?? 'error'" variant="flat" @click="emit('confirm'); open = false">{{ confirmLabel ?? t.common.delete }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
