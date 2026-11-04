<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useKiosk } from '@/composables/kiosk'

// The active tab's text field on the kiosk. Typing anywhere on the page lands here (KioskView moves the
// keys over), and a scan clears it again so scanned digits never stay behind as search text.
const text = defineModel<string>({ default: '' })
defineProps<{ placeholder: string; icon?: string }>()
const emit = defineEmits<{ submit: [string]; move: [1 | -1] }>()
const kiosk = useKiosk()

const field = ref<{ $el: HTMLElement } | null>(null)
let input: HTMLInputElement | null = null
onMounted(() => {
  input = field.value?.$el.querySelector('input') ?? null
  kiosk.focusTarget.value = input
})
onBeforeUnmount(() => {
  if (kiosk.focusTarget.value === input) kiosk.focusTarget.value = null
})
watch(kiosk.scanSeq, () => {
  text.value = ''
  input?.blur()
})

function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault()
    emit('submit', text.value.trim())
  } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault()
    emit('move', e.key === 'ArrowDown' ? 1 : -1)
  } else if (e.key === 'Escape') {
    text.value = ''
    input?.blur()
  }
}
</script>

<template>
  <v-text-field
    ref="field"
    v-model="text"
    :placeholder="placeholder"
    :prepend-inner-icon="icon ?? 'mdi-magnify'"
    variant="solo-filled"
    flat
    hide-details
    clearable
    autocomplete="off"
    spellcheck="false"
    class="kiosk-input"
    @keydown="onKey"
  />
</template>

<style scoped>
.kiosk-input :deep(input) {
  font-size: 1.25rem;
  min-height: 60px;
}
</style>
