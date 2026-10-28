<script setup lang="ts">
import { fileUrl } from '@/api'
import { layerIcon } from '@/composables/wardrobe'

// Garment photos are cut-outs, so they sit on a soft tile and are never cropped.
withDefaults(defineProps<{ photoId?: string | null; layer?: string | null; full?: boolean; rounded?: string; iconSize?: number }>(), {
  photoId: null,
  layer: null,
  full: false,
  rounded: 'lg',
  iconSize: 32,
})
</script>

<template>
  <v-sheet color="surface-container" :rounded="rounded" class="garment-thumb">
    <v-img v-if="photoId" :src="fileUrl(photoId, !full)" :aspect-ratio="1" class="garment-thumb__img">
      <template #placeholder>
        <div class="d-flex align-center justify-center fill-height"><v-progress-circular indeterminate size="20" width="2" color="primary" /></div>
      </template>
    </v-img>
    <v-responsive v-else :aspect-ratio="1">
      <div class="d-flex align-center justify-center fill-height">
        <v-icon :icon="(layer && layerIcon[layer]) || 'mdi-hanger'" :size="iconSize" class="opacity-50" />
      </div>
    </v-responsive>
  </v-sheet>
</template>

<style scoped>
.garment-thumb {
  overflow: hidden;
  position: relative;
}
.garment-thumb__img :deep(.v-img__img) {
  object-fit: contain;
  padding: 6%;
}
</style>
