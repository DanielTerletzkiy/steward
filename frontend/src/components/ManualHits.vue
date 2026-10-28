<script setup lang="ts">
import { fileUrl } from '@/api'
import { t } from '@/i18n'
import type { ManualHit } from '@/types'

withDefaults(defineProps<{ hits: ManualHit[]; showEquipment?: boolean }>(), { showEquipment: true })

/** Split a snippet into plain and «matched» parts, rendered without v-html. */
function parts(snippet: string): { text: string; hit: boolean }[] {
  const out: { text: string; hit: boolean }[] = []
  const re = /«([^»]*)»/g
  let last = 0
  for (let m = re.exec(snippet); m; m = re.exec(snippet)) {
    if (m.index > last) out.push({ text: snippet.slice(last, m.index), hit: false })
    out.push({ text: m[1], hit: true })
    last = m.index + m[0].length
  }
  if (last < snippet.length) out.push({ text: snippet.slice(last), hit: false })
  return out
}
const link = (h: ManualHit) => `${fileUrl(h.file_id)}#page=${h.page}`
</script>

<template>
  <v-list bg-color="transparent" lines="three" class="py-0">
    <template v-for="(h, i) in hits" :key="`${h.file_id}-${h.page}-${i}`">
      <v-divider v-if="i > 0" />
      <v-list-item :href="link(h)" target="_blank" rel="noopener" class="py-3">
        <template #prepend>
          <v-avatar color="primary" variant="tonal" rounded="lg"><v-icon icon="mdi-book-open-page-variant-outline" /></v-avatar>
        </template>
        <div class="d-flex flex-wrap align-center ga-1 text-body-2 font-weight-medium">
          <span v-if="showEquipment">{{ h.equipment_name }}</span>
          <span v-if="showEquipment" class="text-medium-emphasis">·</span>
          <span :class="showEquipment ? 'text-medium-emphasis' : ''">{{ h.document_title }}</span>
          <v-chip size="x-small" variant="tonal" color="primary" label class="ml-1">{{ t.equipment.page(h.page) }}</v-chip>
        </div>
        <div class="text-body-2 mt-1 snippet">
          <template v-for="(p, j) in parts(h.snippet)" :key="j"><mark v-if="p.hit" class="highlight">{{ p.text }}</mark><template v-else>{{ p.text }}</template></template>
        </div>
        <template #append><v-icon icon="mdi-open-in-new" size="18" class="text-medium-emphasis" /></template>
      </v-list-item>
    </template>
  </v-list>
</template>

<style scoped>
.snippet {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  line-height: 1.5;
}
</style>
