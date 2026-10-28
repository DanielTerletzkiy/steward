<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { api, fileUrl } from '@/api'
import { LOCALE, t } from '@/i18n'
import { useCatalog } from '@/composables/catalog'
import { attempt, notify } from '@/composables/notify'
import PhotoPicker from './PhotoPicker.vue'
import type { Chore, Equipment, EquipmentIn } from '@/types'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ equipment?: Equipment | null; rooms?: string[] }>()
const emit = defineEmits<{ saved: [Equipment] }>()
const { xs } = useDisplay()
const { state } = useCatalog()

const blank = () => ({
  name: '',
  brand: '',
  model: '',
  serial: '',
  room: null as string | null,
  ha_device_id: '',
  purchased_on: '' as string | null,
  price: '' as string | number,
  shop: '',
  warranty_until: '' as string | null,
  notes: '',
  consumable_ids: [] as number[],
  chore_ids: [] as number[],
})
const form = ref(blank())
const photo = ref<File | null>(null)
const removePhoto = ref(false)
const chores = shallowRef<Chore[]>([])
const busy = ref(false)
const isEdit = computed(() => !!props.equipment)
const requiredRule = [(v: string | null) => !!v?.trim() || t.common.required]

watch(open, async (v) => {
  if (!v) return
  photo.value = null
  removePhoto.value = false
  const e = props.equipment
  form.value = e
    ? {
        name: e.name,
        brand: e.brand ?? '',
        model: e.model ?? '',
        serial: e.serial ?? '',
        room: e.room,
        ha_device_id: e.ha_device_id ?? '',
        purchased_on: e.purchased_on ?? '',
        price: e.price ?? '',
        shop: e.shop ?? '',
        warranty_until: e.warranty_until ?? '',
        notes: e.notes ?? '',
        consumable_ids: [...e.consumable_ids],
        chore_ids: [...e.chore_ids],
      }
    : blank()
  chores.value = ((await attempt(() => api.chores())) ?? []).sort((a, b) => a.name.localeCompare(b.name, LOCALE))
})

const roomItems = computed(() => [...new Set((props.rooms ?? []).filter(Boolean))].sort((a, b) => a.localeCompare(b, LOCALE)))
const text = (v: string | null | undefined) => (v ?? '').trim() || null

async function save() {
  const f = form.value
  if (!f.name.trim()) return
  busy.value = true
  const price = f.price === '' || f.price == null ? null : Number(String(f.price).replace(',', '.'))
  const body: EquipmentIn = {
    name: f.name.trim(),
    brand: text(f.brand),
    model: text(f.model),
    serial: text(f.serial),
    room: text(f.room),
    ha_device_id: text(f.ha_device_id),
    purchased_on: f.purchased_on || null,
    price: price != null && Number.isFinite(price) ? price : null,
    shop: text(f.shop),
    warranty_until: f.warranty_until || null,
    notes: text(f.notes),
    consumable_ids: f.consumable_ids,
    chore_ids: f.chore_ids,
  }
  let saved = await attempt(() => (props.equipment ? api.updateEquipment(props.equipment.id, body) : api.createEquipment(body)))
  if (saved && photo.value) {
    const withPhoto = await attempt(() => api.setEquipmentPhoto(saved!.id, photo.value!))
    if (withPhoto) saved = withPhoto
  } else if (saved && removePhoto.value && saved.photo_id) {
    const without = await attempt(() => api.deleteEquipmentPhoto(saved!.id))
    if (without) saved = without
  }
  busy.value = false
  if (saved) {
    notify(t.equipment.saved)
    emit('saved', saved)
    open.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" :fullscreen="xs" max-width="720" scrollable>
    <v-card :rounded="xs ? 0 : 'xl'">
      <v-toolbar color="transparent" density="comfortable">
        <v-btn icon="mdi-close" :title="t.common.close" @click="open = false" />
        <v-toolbar-title class="font-weight-medium">{{ isEdit ? t.equipment.editItem : t.equipment.newItem }}</v-toolbar-title>
        <template v-if="xs" #append>
          <v-btn color="primary" variant="flat" class="mr-2" :loading="busy" @click="save">{{ t.common.save }}</v-btn>
        </template>
      </v-toolbar>
      <v-divider />
      <v-card-text class="pt-4">
        <v-form @submit.prevent="save">
          <v-row>
            <v-col cols="12" sm="4">
              <PhotoPicker v-model="photo" :current-url="equipment?.photo_id && !removePhoto ? fileUrl(equipment.photo_id, true) : null" icon="mdi-washing-machine" removable @remove="removePhoto = true" />
            </v-col>
            <v-col cols="12" sm="8">
              <v-text-field v-model="form.name" :label="t.common.name" :rules="requiredRule" :autofocus="!xs" />
              <v-row dense>
                <v-col cols="6"><v-text-field v-model="form.brand" :label="t.common.brand" /></v-col>
                <v-col cols="6"><v-text-field v-model="form.model" :label="t.equipment.model" /></v-col>
                <v-col cols="12"><v-combobox v-model="form.room" :items="roomItems" :label="t.equipment.room" prepend-inner-icon="mdi-floor-plan" /></v-col>
              </v-row>
            </v-col>
          </v-row>
          <v-row dense>
            <v-col cols="6" sm="4"><v-text-field v-model="form.purchased_on" type="date" :label="t.equipment.purchasedOn" /></v-col>
            <v-col cols="6" sm="4"><v-text-field v-model="form.price" :label="t.common.price" inputmode="decimal" suffix="€" /></v-col>
            <v-col cols="12" sm="4"><v-text-field v-model="form.shop" :label="t.equipment.shop" /></v-col>
            <v-col cols="6"><v-text-field v-model="form.warranty_until" type="date" :label="t.equipment.warrantyUntil" prepend-inner-icon="mdi-shield-check-outline" /></v-col>
            <v-col cols="6"><v-text-field v-model="form.serial" :label="t.equipment.serial" /></v-col>
            <v-col cols="12">
              <v-autocomplete
                v-model="form.consumable_ids"
                :items="state.products"
                item-title="name"
                item-value="id"
                :label="t.equipment.pickConsumables"
                prepend-inner-icon="mdi-package-variant-closed"
                multiple
                chips
                closable-chips
              />
            </v-col>
            <v-col cols="12">
              <v-autocomplete
                v-model="form.chore_ids"
                :items="chores"
                item-title="name"
                item-value="id"
                :label="t.equipment.pickChores"
                prepend-inner-icon="mdi-broom"
                multiple
                chips
                closable-chips
              />
            </v-col>
            <v-col cols="12"><v-text-field v-model="form.ha_device_id" :label="t.equipment.haDevice" prepend-inner-icon="mdi-home-assistant" /></v-col>
            <v-col cols="12"><v-textarea v-model="form.notes" :label="t.equipment.notes" rows="2" auto-grow /></v-col>
          </v-row>
          <button type="submit" hidden />
        </v-form>
      </v-card-text>
      <template v-if="!xs">
        <v-divider />
        <v-card-actions class="px-4">
          <v-spacer />
          <v-btn @click="open = false">{{ t.common.cancel }}</v-btn>
          <v-btn color="primary" variant="flat" :loading="busy" @click="save">{{ isEdit ? t.common.save : t.common.create }}</v-btn>
        </v-card-actions>
      </template>
    </v-card>
  </v-dialog>
</template>
