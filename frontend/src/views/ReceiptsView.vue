<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/api'
import { t } from '@/i18n'
import { useResource } from '@/composables/resource'
import { attempt, notify } from '@/composables/notify'
import { formatDateTime, formatEuro } from '@/composables/format'
import EmptyState from '@/components/EmptyState.vue'
import type { ReceiptSummary } from '@/types'

const router = useRouter()
const { data: receipts, loading, error, reload } = useResource<ReceiptSummary[]>(() => api.receipts(), ['receipts'], [])
const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const dragging = ref(false)

async function upload(file: File | undefined) {
  if (!file) return
  uploading.value = true
  const res = await attempt(() => api.uploadReceipt(file))
  uploading.value = false
  if (fileInput.value) fileInput.value.value = ''
  if (res) {
    notify(t.receipts.uploaded)
    router.push(`/receipts/${res.id}`)
  }
}
function onDrop(e: DragEvent) {
  dragging.value = false
  upload(e.dataTransfer?.files?.[0])
}
</script>

<template>
  <div class="page" style="max-width: 900px" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop">
    <div class="d-flex align-center mb-4">
      <div>
        <div class="page-title">{{ t.receipts.title }}</div>
        <div class="text-body-2 text-medium-emphasis">{{ receipts.length }} eBons</div>
      </div>
      <v-spacer />
      <input ref="fileInput" type="file" accept="application/pdf,.pdf" hidden @change="upload(($event.target as HTMLInputElement).files?.[0])" />
      <v-btn color="primary" variant="flat" prepend-icon="mdi-file-upload-outline" :loading="uploading" @click="fileInput?.click()">{{ t.receipts.upload }}</v-btn>
    </div>

    <v-alert v-if="error" type="error" variant="tonal" :text="error" class="mb-3">
      <template #append><v-btn variant="text" @click="reload">{{ t.app.retry }}</v-btn></template>
    </v-alert>

    <v-sheet v-if="dragging" border="dashed md primary" rounded="xl" class="pa-8 mb-4 text-center text-primary">
      <v-icon icon="mdi-file-pdf-box" size="40" /><div>PDF hier ablegen</div>
    </v-sheet>

    <v-skeleton-loader v-if="loading && !receipts.length" type="list-item-two-line@4" class="rounded-xl" />
    <EmptyState v-else-if="!receipts.length" icon="mdi-receipt-text-outline" :title="t.receipts.empty" :text="t.receipts.emptyHint">
      <v-btn color="primary" variant="tonal" prepend-icon="mdi-file-upload-outline" @click="fileInput?.click()">{{ t.receipts.upload }}</v-btn>
    </EmptyState>

    <v-card v-else variant="flat" border>
      <v-list lines="two" bg-color="transparent">
        <template v-for="(r, idx) in receipts" :key="r.id">
          <v-divider v-if="idx > 0" inset />
          <v-list-item :to="`/receipts/${r.id}`" class="py-3">
            <template #prepend>
              <v-avatar color="primary" variant="tonal"><v-icon icon="mdi-receipt-text-outline" /></v-avatar>
            </template>
            <v-list-item-title class="font-weight-medium">{{ formatDateTime(r.at) }}</v-list-item-title>
            <v-list-item-subtitle>{{ r.store ?? r.chain }}</v-list-item-subtitle>
            <div class="d-flex flex-wrap ga-1 mt-2">
              <v-chip color="success" variant="tonal" prepend-icon="mdi-link-variant" label>{{ t.receipts.matched(r.matched) }}</v-chip>
              <v-chip v-if="r.unmatched" color="warning" variant="tonal" prepend-icon="mdi-link-variant-off" label>{{ t.receipts.unmatched(r.unmatched) }}</v-chip>
              <v-chip v-if="r.stocked" color="primary" variant="tonal" prepend-icon="mdi-fridge-outline" label>{{ t.receipts.stocked }}</v-chip>
              <v-chip v-else variant="outlined" prepend-icon="mdi-fridge-off-outline" label>{{ t.receipts.notStocked }}</v-chip>
            </div>
            <template #append>
              <div class="text-h6 font-weight-bold text-tabular ml-2">{{ formatEuro(r.total) }}</div>
            </template>
          </v-list-item>
        </template>
      </v-list>
    </v-card>
  </div>
</template>
