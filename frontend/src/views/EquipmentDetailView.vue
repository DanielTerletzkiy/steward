<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, ApiError, fileUrl } from '@/api'
import { t } from '@/i18n'
import { onTopics } from '@/composables/live'
import { useResource } from '@/composables/resource'
import { useCatalog } from '@/composables/catalog'
import { attempt, notify } from '@/composables/notify'
import { preparePhoto } from '@/composables/photos'
import { formatAmount, formatDate, formatDateTime, formatEuro, mdiIcon, parseDateTime, relativeDue, relativeTime } from '@/composables/format'
import { docIcon, formatSize, useManualSearch, warrantyChip } from '@/composables/equipment'
import EmptyState from '@/components/EmptyState.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import EquipmentDialog from '@/components/EquipmentDialog.vue'
import ManualHits from '@/components/ManualHits.vue'
import ApplianceLiveCard from '@/components/ApplianceLiveCard.vue'
import EquipmentHaCard from '@/components/EquipmentHaCard.vue'
import type { Chore, Equipment, EquipmentDocument, EquipmentRun, StockItem } from '@/types'

const props = defineProps<{ id: number }>()
const router = useRouter()
const { productsById } = useCatalog()

const item = ref<Equipment | null>(null)
const error = ref<string | null>(null)
const notFound = ref(false)
async function load() {
  try {
    item.value = await api.equipment(props.id)
    error.value = null
    notFound.value = false
  } catch (e) {
    notFound.value = e instanceof ApiError && e.status === 404
    error.value = e instanceof Error ? e.message : String(e)
  }
}
watch(() => props.id, load, { immediate: true })
onTopics(['equipment'], load)

const runs = ref<EquipmentRun[]>([])
async function loadRuns() {
  runs.value = (await api.equipmentRuns(props.id, 8).catch(() => null)) ?? []
}
watch(() => props.id, loadRuns, { immediate: true })
onTopics(['equipment'], loadRuns)
const runSource = (r: EquipmentRun) => (r.source ? t.appliances.runSources[r.source] ?? r.source : null)

const { data: chores } = useResource<Chore[]>(() => api.chores(), ['chores'], [])
const { data: stock } = useResource<StockItem[]>(() => api.stock(true), ['stock', 'catalog'], [])
const { data: all } = useResource<Equipment[]>(() => api.equipmentList(), ['equipment'], [])
const rooms = computed(() => all.value.map((e) => e.room).filter((r): r is string => !!r))

const linkedChores = computed(() => {
  const byId = new Map(chores.value.map((c) => [c.id, c]))
  return (item.value?.chore_ids ?? []).map((id) => byId.get(id)).filter((c): c is Chore => !!c)
})
const consumables = computed(() => {
  const stockById = new Map(stock.value.map((s) => [s.product.id, s]))
  return (item.value?.consumable_ids ?? []).map((id) => ({ id, product: productsById.value.get(id), stock: stockById.get(id) }))
})
const warranty = computed(() => (item.value ? warrantyChip(item.value) : null))
const facts = computed(() => {
  const e = item.value
  if (!e) return []
  return [
    { icon: 'mdi-calendar', label: t.equipment.purchasedOn, value: e.purchased_on ? formatDate(e.purchased_on) : null },
    { icon: 'mdi-currency-eur', label: t.common.price, value: e.price != null ? formatEuro(e.price) : null },
    { icon: 'mdi-storefront-outline', label: t.equipment.shop, value: e.shop },
    { icon: 'mdi-shield-check-outline', label: t.equipment.warrantyUntil, value: e.warranty_until ? formatDate(e.warranty_until) : null },
    { icon: 'mdi-barcode', label: t.equipment.serial, value: e.serial },
    { icon: 'mdi-home-assistant', label: t.equipment.haDevice, value: e.ha_device_id },
  ].filter((f) => f.value)
})
const hasPdf = computed(() => item.value?.documents.some((d) => d.file.content_type === 'application/pdf') ?? false)

// --- photo
const photoInput = ref<HTMLInputElement | null>(null)
const photoBusy = ref(false)
async function photoPicked(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !item.value) return
  photoBusy.value = true
  const res = await attempt(async () => api.setEquipmentPhoto(props.id, await preparePhoto(file)))
  photoBusy.value = false
  if (res) {
    item.value = res
    notify(t.equipment.photoSaved)
  }
}

async function removePhoto() {
  const res = await attempt(() => api.deleteEquipmentPhoto(props.id))
  if (res) {
    item.value = res
    notify(t.common.photoRemoved)
  }
}

// --- documents
const uploadOpen = ref(false)
const upload = ref({ file: null as File | File[] | null, kind: 'manual', title: '' })
const uploading = ref(false)
const kinds = Object.entries(t.equipment.kinds).map(([value, title]) => ({ value, title }))
function openUpload() {
  upload.value = { file: null, kind: 'manual', title: '' }
  uploadOpen.value = true
}
async function doUpload() {
  const f = Array.isArray(upload.value.file) ? upload.value.file[0] : upload.value.file
  if (!f) return
  uploading.value = true
  const ok = !!(await attempt(() => api.addEquipmentDocument(props.id, f, upload.value.kind, upload.value.title.trim() || null)))
  uploading.value = false
  if (ok) {
    notify(t.equipment.uploaded)
    uploadOpen.value = false
    load()
  }
}
const deleteDoc = ref<EquipmentDocument | null>(null)
const confirmDoc = ref(false)
async function removeDoc() {
  const d = deleteDoc.value
  if (!d) return
  const ok = await attempt(async () => (await api.deleteEquipmentDocument(props.id, d.id), true))
  if (ok) {
    notify(t.equipment.docDeleted)
    load()
  }
}

// --- edit / delete
const editOpen = ref(false)
const confirmDelete = ref(false)
async function remove() {
  const ok = await attempt(async () => (await api.deleteEquipment(props.id), true))
  if (ok) {
    notify(t.equipment.deleted)
    router.push('/equipment')
  }
}

const search = useManualSearch(() => props.id)
const searchQuery = search.query
</script>

<template>
  <div class="page" style="max-width: 1100px">
    <v-btn variant="text" prepend-icon="mdi-arrow-left" to="/equipment" class="mb-2 ml-n3">{{ t.equipment.title }}</v-btn>

    <EmptyState v-if="notFound" icon="mdi-help-circle-outline" :title="t.equipment.notFound" />
    <v-alert v-else-if="error && !item" type="error" variant="tonal" :text="error" />
    <v-skeleton-loader v-else-if="!item" type="article, list-item@4" class="rounded-xl" />

    <template v-else>
      <v-card variant="flat" color="surface-container" class="mb-4">
        <div class="d-flex flex-column flex-sm-row">
          <div class="pa-3 pb-0 pb-sm-3 flex-shrink-0">
            <v-sheet color="surface" rounded="lg" class="overflow-hidden position-relative photo-box">
              <v-img v-if="item.photo_id" :src="fileUrl(item.photo_id)" cover class="fill-height" />
              <div v-else class="d-flex align-center justify-center fill-height clickable" @click="photoInput?.click()">
                <v-icon icon="mdi-washing-machine" size="56" class="opacity-40" />
              </div>
              <v-btn
                icon="mdi-camera-outline"
                size="small"
                variant="flat"
                color="surface"
                class="photo-btn"
                :loading="photoBusy"
                :title="item.photo_id ? t.equipment.replacePhoto : t.equipment.addPhoto"
                @click="photoInput?.click()"
              />
              <input ref="photoInput" type="file" accept="image/*" hidden @change="photoPicked" />
            </v-sheet>
          </div>
          <div class="flex-grow-1 min-w-0 d-flex flex-column">
            <v-card-item>
              <v-card-title class="text-h6 font-weight-medium" style="white-space: normal">{{ item.name }}</v-card-title>
              <v-card-subtitle v-if="item.brand || item.model">{{ [item.brand, item.model].filter(Boolean).join(' · ') }}</v-card-subtitle>
              <template #append>
                <v-menu location="bottom end">
                  <template #activator="{ props: menuProps }"><v-btn v-bind="menuProps" icon="mdi-dots-vertical" variant="text" /></template>
                  <v-list density="compact">
                    <v-list-item prepend-icon="mdi-pencil-outline" :title="t.common.edit" @click="editOpen = true" />
                    <v-list-item prepend-icon="mdi-camera-outline" :title="item.photo_id ? t.equipment.replacePhoto : t.equipment.addPhoto" @click="photoInput?.click()" />
                    <v-list-item v-if="item.photo_id" prepend-icon="mdi-image-remove-outline" :title="t.common.removePhoto" @click="removePhoto" />
                    <v-divider />
                    <v-list-item prepend-icon="mdi-delete-outline" base-color="error" :title="t.equipment.deleteItem" @click="confirmDelete = true" />
                  </v-list>
                </v-menu>
              </template>
            </v-card-item>
            <v-card-text class="pt-0">
              <div class="d-flex flex-wrap ga-1">
                <v-chip v-if="item.room" variant="outlined" prepend-icon="mdi-floor-plan" label>{{ item.room }}</v-chip>
                <v-chip v-if="warranty" :color="warranty.color" :variant="warranty.variant" :prepend-icon="warranty.icon" label :class="warranty.muted ? 'opacity-60' : ''">
                  {{ warranty.text }}
                </v-chip>
              </div>
            </v-card-text>
            <v-spacer />
            <v-card-actions class="px-4 pb-3">
              <v-btn variant="tonal" color="primary" prepend-icon="mdi-pencil-outline" @click="editOpen = true">{{ t.common.edit }}</v-btn>
            </v-card-actions>
          </div>
        </div>
      </v-card>

      <ApplianceLiveCard v-if="item.live" :equipment="item" class="mb-4" />

      <v-row>
        <v-col cols="12" md="7">
          <!-- Documents -->
          <v-card variant="flat" border class="mb-4">
            <v-card-item prepend-icon="mdi-paperclip">
              <v-card-title class="text-subtitle-1 font-weight-medium">{{ t.equipment.documents }}</v-card-title>
              <template #append>
                <v-btn variant="tonal" color="primary" size="small" prepend-icon="mdi-upload" @click="openUpload">{{ t.equipment.upload }}</v-btn>
              </template>
            </v-card-item>
            <EmptyState v-if="!item.documents.length" compact icon="mdi-file-document-outline" :title="t.equipment.noDocuments" />
            <v-list v-else bg-color="transparent" lines="two">
              <v-list-item v-for="d in item.documents" :key="d.id" :href="fileUrl(d.file.id)" target="_blank" rel="noopener">
                <template #prepend>
                  <v-avatar :color="d.kind === 'invoice' ? 'secondary' : 'primary'" variant="tonal" rounded="lg"><v-icon :icon="docIcon(d.file.content_type)" /></v-avatar>
                </template>
                <v-list-item-title class="font-weight-medium wrap">{{ d.title }}</v-list-item-title>
                <v-list-item-subtitle>
                  {{ t.equipment.kinds[d.kind] ?? d.kind }}
                  <template v-if="d.file.pages"> · {{ t.equipment.pages(d.file.pages) }}</template>
                  · {{ formatSize(d.file.size) }}
                </v-list-item-subtitle>
                <template #append>
                  <v-btn icon="mdi-delete-outline" variant="text" size="small" :title="t.equipment.deleteDoc" @click.prevent.stop="deleteDoc = d; confirmDoc = true" />
                </template>
              </v-list-item>
            </v-list>
          </v-card>

          <!-- Facts -->
          <v-card v-if="facts.length" variant="flat" border class="mb-4">
            <v-card-item prepend-icon="mdi-information-outline">
              <v-card-title class="text-subtitle-1 font-weight-medium">{{ t.equipment.facts }}</v-card-title>
            </v-card-item>
            <v-row dense class="px-4 pb-4">
              <v-col v-for="f in facts" :key="f.label" cols="6" sm="4">
                <div class="text-caption text-medium-emphasis d-flex align-center"><v-icon :icon="f.icon" size="14" class="mr-1" />{{ f.label }}</div>
                <div class="text-body-2 font-weight-medium text-tabular" style="word-break: break-word">{{ f.value }}</div>
              </v-col>
            </v-row>
          </v-card>

          <v-card v-if="item.notes" variant="flat" border class="mb-4">
            <v-card-item prepend-icon="mdi-note-text-outline">
              <v-card-title class="text-subtitle-1 font-weight-medium">{{ t.equipment.notes }}</v-card-title>
            </v-card-item>
            <v-card-text class="pt-0" style="white-space: pre-line">{{ item.notes }}</v-card-text>
          </v-card>
        </v-col>

        <v-col cols="12" md="5">
          <EquipmentHaCard :equipment="item" class="mb-4" @updated="(e) => (item = e)" />

          <!-- Runs -->
          <v-card v-if="item.run_count || runs.length" variant="flat" border class="mb-4">
            <v-card-item prepend-icon="mdi-history">
              <v-card-title class="text-subtitle-1 font-weight-medium">{{ t.appliances.runs }}</v-card-title>
              <v-card-subtitle>
                {{ t.appliances.runCount(item.run_count) }}<template v-if="item.last_run_at"> · {{ t.appliances.lastRun(relativeTime(item.last_run_at)) }}</template>
              </v-card-subtitle>
            </v-card-item>
            <v-list v-if="runs.length" density="compact" bg-color="transparent" class="pt-0">
              <v-list-item v-for="r in runs" :key="r.id" prepend-icon="mdi-check-circle-outline" :title="formatDateTime(r.finished_at)" :subtitle="[runSource(r), r.detail].filter(Boolean).join(' · ') || undefined">
                <template #append><span class="text-caption text-medium-emphasis">{{ relativeTime(r.finished_at) }}</span></template>
              </v-list-item>
            </v-list>
          </v-card>

          <!-- Manual search -->
          <v-card v-if="hasPdf" variant="flat" border class="mb-4">
            <div class="pa-3">
              <v-text-field
                v-model="searchQuery"
                :placeholder="t.equipment.askHere"
                prepend-inner-icon="mdi-text-box-search-outline"
                :loading="search.searching.value"
                clearable
                hide-details
                density="compact"
                variant="solo-filled"
                flat
                rounded="pill"
                @keydown.enter="search.now()"
              />
            </div>
            <template v-if="search.searched.value && (searchQuery ?? '').trim().length >= 2">
              <v-alert v-if="search.error.value" type="error" variant="tonal" density="compact" class="mx-3 mb-3" :text="search.error.value" />
              <EmptyState v-else-if="!search.hits.value.length" compact icon="mdi-book-off-outline" :title="t.equipment.noHits" />
              <ManualHits v-else :hits="search.hits.value" :show-equipment="false" />
            </template>
          </v-card>

          <!-- Upkeep chores -->
          <v-card variant="flat" border class="mb-4">
            <v-card-item prepend-icon="mdi-broom">
              <v-card-title class="text-subtitle-1 font-weight-medium">{{ t.equipment.chores }}</v-card-title>
            </v-card-item>
            <EmptyState v-if="!linkedChores.length" compact icon="mdi-broom" :title="t.equipment.noChores" />
            <v-list v-else bg-color="transparent" density="comfortable">
              <v-list-item v-for="c in linkedChores" :key="c.id" :prepend-icon="mdiIcon(c.icon)" to="/chores" :title="c.name">
                <v-list-item-subtitle>
                  <span :class="c.status === 'overdue' ? 'text-error' : c.status === 'due_today' ? 'text-warning' : ''">
                    {{ c.next_due ? relativeDue(parseDateTime(c.next_due)) : t.status.manual }}
                  </span>
                </v-list-item-subtitle>
              </v-list-item>
            </v-list>
            <v-card-actions v-if="linkedChores.length"><v-btn variant="text" to="/chores" append-icon="mdi-chevron-right">{{ t.equipment.allChores }}</v-btn></v-card-actions>
          </v-card>

          <!-- Consumables -->
          <v-card variant="flat" border class="mb-4">
            <v-card-item prepend-icon="mdi-package-variant-closed">
              <v-card-title class="text-subtitle-1 font-weight-medium">{{ t.equipment.consumables }}</v-card-title>
            </v-card-item>
            <EmptyState v-if="!consumables.length" compact icon="mdi-package-variant" :title="t.equipment.noConsumables" />
            <v-list v-else bg-color="transparent" density="comfortable">
              <v-list-item v-for="c in consumables" :key="c.id" to="/stock" :title="c.product?.name ?? `#${c.id}`">
                <template #prepend>
                  <v-avatar :color="c.stock && c.stock.amount > 0 ? (c.stock.below_min ? 'warning' : 'primary') : 'grey'" variant="tonal" size="36" class="font-weight-bold">
                    {{ (c.product?.name ?? '?').charAt(0).toUpperCase() }}
                  </v-avatar>
                </template>
                <v-list-item-subtitle>
                  <span v-if="c.stock && c.stock.amount > 0" :class="c.stock.below_min ? 'text-warning' : ''">{{ t.equipment.inStock(formatAmount(c.stock.amount, c.product?.unit)) }}</span>
                  <span v-else class="text-error">{{ t.equipment.outOfStock }}</span>
                </v-list-item-subtitle>
              </v-list-item>
            </v-list>
          </v-card>
        </v-col>
      </v-row>

      <v-dialog v-model="uploadOpen" max-width="480">
        <v-card :title="t.equipment.uploadTitle" prepend-icon="mdi-upload">
          <v-card-text>
            <v-file-input v-model="upload.file" :label="t.equipment.file" accept="application/pdf,image/*" prepend-icon="" prepend-inner-icon="mdi-paperclip" show-size />
            <v-select v-model="upload.kind" :items="kinds" :label="t.equipment.kind" />
            <v-text-field v-model="upload.title" :label="t.equipment.docTitle" :hint="t.equipment.docTitleHint" persistent-hint />
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn @click="uploadOpen = false">{{ t.common.cancel }}</v-btn>
            <v-btn color="primary" variant="flat" :loading="uploading" :disabled="!upload.file || (Array.isArray(upload.file) && !upload.file.length)" @click="doUpload">{{ t.equipment.upload }}</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <EquipmentDialog v-model="editOpen" :equipment="item" :rooms="rooms" @saved="(e) => (item = e)" />
      <ConfirmDialog v-model="confirmDelete" :title="t.equipment.deleteItem" :text="t.equipment.confirmDelete(item.name)" @confirm="remove" />
      <ConfirmDialog v-model="confirmDoc" :title="t.equipment.deleteDoc" :text="t.equipment.confirmDeleteDoc(deleteDoc?.title ?? '')" @confirm="removeDoc" />
    </template>
  </div>
</template>

<style scoped>
.photo-box {
  width: 100%;
  aspect-ratio: 4 / 3;
}
@media (min-width: 600px) {
  .photo-box {
    width: 200px;
    height: 200px;
    aspect-ratio: auto;
  }
}
.photo-btn {
  position: absolute;
  right: 8px;
  bottom: 8px;
}
</style>
