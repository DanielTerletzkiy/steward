<script setup lang="ts">
import { computed } from 'vue'
import { t } from '@/i18n'
import { label } from '@/composables/wardrobe'
import GarmentThumb from './GarmentThumb.vue'
import type { Garment } from '@/types'

// `row` lays the pieces out side by side, each at most `tile` px wide; otherwise a 2- or 3-column grid fills the width.
const props = withDefaults(defineProps<{ ids: number[]; garments: Map<number, Garment>; max?: number; row?: boolean; tile?: number }>(), {
  max: 6,
  row: false,
  tile: 96,
})

const pieces = computed(() => props.ids.map((id) => ({ id, g: props.garments.get(id) })))
const shown = computed(() => pieces.value.slice(0, props.max))
const extra = computed(() => Math.max(0, pieces.value.length - props.max))
const template = computed(() =>
  props.row
    ? `repeat(${shown.value.length || 1}, minmax(0, ${props.tile}px))`
    : `repeat(${shown.value.length <= 4 ? 2 : 3}, minmax(0, 1fr))`,
)
</script>

<template>
  <div class="collage" :style="{ gridTemplateColumns: template }">
    <div v-for="(p, i) in shown" :key="`${p.id}-${i}`" class="collage__tile" :title="p.g ? `${p.g.name} · ${label.category(p.g.category)}` : t.wardrobe.missingPiece">
      <GarmentThumb :photo-id="p.g?.photo_id" :layer="p.g?.layer" :icon-size="22" rounded="lg" />
      <div v-if="extra && i === shown.length - 1" class="collage__more text-subtitle-2 font-weight-bold">+{{ extra }}</div>
    </div>
  </div>
</template>

<style scoped>
.collage {
  display: grid;
  gap: 6px;
}
.collage__tile {
  position: relative;
  min-width: 0;
}
.collage__more {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
}
</style>
