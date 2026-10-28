<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { t } from '@/i18n'

// Take a photo with the camera or pick one from the device, with a preview.
const file = defineModel<File | null>({ default: null })
const props = withDefaults(defineProps<{ currentUrl?: string | null; contain?: boolean; icon?: string; aspect?: number; removable?: boolean }>(), {
  currentUrl: null,
  contain: false,
  icon: 'mdi-image-outline',
  aspect: 1,
  removable: false,
})
const emit = defineEmits<{ remove: [] }>()

/** Drop a newly picked photo first; otherwise ask the parent to remove the stored one. */
function remove() {
  if (file.value) file.value = null
  else emit('remove')
}

const cameraInput = ref<HTMLInputElement | null>(null)
const galleryInput = ref<HTMLInputElement | null>(null)
const preview = ref<string | null>(null)

watch(
  file,
  (f) => {
    if (preview.value) URL.revokeObjectURL(preview.value)
    preview.value = f ? URL.createObjectURL(f) : null
  },
  { immediate: true },
)
onBeforeUnmount(() => preview.value && URL.revokeObjectURL(preview.value))

function picked(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  if (f) file.value = f
  input.value = ''
}
</script>

<template>
  <div>
    <v-sheet color="surface-container" rounded="xl" class="photo-picker overflow-hidden">
      <v-img v-if="preview || props.currentUrl" :src="preview ?? props.currentUrl ?? undefined" :aspect-ratio="aspect" :cover="!contain" :class="contain ? 'photo-picker__contain' : ''" />
      <v-responsive v-else :aspect-ratio="aspect">
        <div class="d-flex flex-column align-center justify-center fill-height text-medium-emphasis clickable" @click="galleryInput?.click()">
          <v-icon :icon="icon" size="48" class="mb-2 opacity-60" />
          <div class="text-body-2">{{ t.wardrobe.noPhoto }}</div>
        </div>
      </v-responsive>
    </v-sheet>
    <div class="d-flex flex-wrap ga-2 mt-2">
      <v-btn class="flex-grow-1" variant="tonal" color="primary" prepend-icon="mdi-camera-outline" @click="cameraInput?.click()">{{ t.wardrobe.takePhoto }}</v-btn>
      <v-btn class="flex-grow-1" variant="tonal" prepend-icon="mdi-image-outline" @click="galleryInput?.click()">{{ t.wardrobe.choosePhoto }}</v-btn>
      <v-btn v-if="removable && (file || props.currentUrl)" variant="tonal" icon="mdi-image-remove-outline" size="small" class="align-self-center" :title="t.common.removePhoto" @click="remove" />
    </div>
    <input ref="cameraInput" type="file" accept="image/*" capture="environment" hidden @change="picked" />
    <input ref="galleryInput" type="file" accept="image/*" hidden @change="picked" />
  </div>
</template>

<style scoped>
.photo-picker__contain :deep(.v-img__img) {
  padding: 4%;
}
</style>
