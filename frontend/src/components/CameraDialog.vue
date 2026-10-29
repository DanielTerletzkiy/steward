<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { t } from '@/i18n'
import { captureFrame } from '@/composables/photos'

// Take a photo with the live camera (getUserMedia). Unlike <input capture>, this also works inside the
// Home Assistant app, which only offers a file picker for file inputs.
const open = defineModel<boolean>({ default: false })
const emit = defineEmits<{ captured: [File]; fallback: [] }>()
const { xs } = useDisplay()

const video = ref<HTMLVideoElement | null>(null)
const running = ref(false)
const starting = ref(false)
const taking = ref(false)
const error = ref<string | null>(null)
const facing = ref<'environment' | 'user'>('environment')
const canSwitch = ref(false)
let stream: MediaStream | null = null

async function start() {
  stop()
  error.value = null
  starting.value = true
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: facing.value }, width: { ideal: 2048 }, height: { ideal: 1536 } },
      audio: false,
    })
    await nextTick()
    if (!video.value) return stop()
    video.value.srcObject = stream
    await video.value.play()
    running.value = true
    const devices = await navigator.mediaDevices.enumerateDevices().catch(() => [])
    canSwitch.value = devices.filter((d) => d.kind === 'videoinput').length > 1
  } catch (e) {
    stop()
    const name = e instanceof DOMException ? e.name : ''
    error.value = name === 'NotAllowedError' ? t.scan.cameraDenied : name === 'NotFoundError' ? t.scan.cameraUnavailable : e instanceof Error ? e.message : String(e)
  } finally {
    starting.value = false
  }
}

function stop() {
  stream?.getTracks().forEach((track) => track.stop())
  stream = null
  if (video.value) video.value.srcObject = null
  running.value = false
}

async function shoot() {
  if (!video.value || !running.value) return
  taking.value = true
  try {
    const file = await captureFrame(video.value)
    navigator.vibrate?.(40)
    emit('captured', file)
    open.value = false
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    taking.value = false
  }
}

function switchCamera() {
  facing.value = facing.value === 'environment' ? 'user' : 'environment'
  start()
}

watch(open, (isOpen) => (isOpen ? start() : stop()))
onBeforeUnmount(stop)
</script>

<template>
  <v-dialog v-model="open" :fullscreen="xs" max-width="720">
    <v-card color="black" class="camera-dialog d-flex flex-column">
      <div class="camera-dialog__view position-relative flex-grow-1">
        <video ref="video" class="camera-dialog__video" :class="{ 'camera-dialog__video--on': running }" muted playsinline />
        <div v-if="!running" class="camera-dialog__overlay text-center pa-6 text-white">
          <v-progress-circular v-if="starting" indeterminate />
          <template v-else-if="error">
            <v-icon icon="mdi-camera-off-outline" size="40" class="mb-2 opacity-80" />
            <div class="text-body-2 mb-3" style="max-width: 360px">{{ error }}</div>
            <div class="d-flex flex-wrap justify-center ga-2">
              <v-btn color="primary" variant="flat" @click="start">{{ t.app.retry }}</v-btn>
              <v-btn variant="tonal" color="white" prepend-icon="mdi-cellphone" @click="open = false; emit('fallback')">{{ t.photo.cameraApp }}</v-btn>
            </div>
          </template>
        </div>
      </div>
      <div class="d-flex align-center justify-space-between pa-4">
        <v-btn variant="text" color="white" @click="open = false">{{ t.common.cancel }}</v-btn>
        <v-btn
          class="camera-dialog__shutter"
          icon
          size="72"
          color="white"
          :disabled="!running"
          :loading="taking"
          :aria-label="t.photo.shoot"
          @click="shoot"
        >
          <v-icon icon="mdi-camera" size="32" color="black" />
        </v-btn>
        <v-btn variant="text" color="white" icon="mdi-camera-flip-outline" :disabled="!canSwitch || !running" :aria-label="t.photo.switchCamera" @click="switchCamera" />
      </div>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.camera-dialog {
  min-height: min(80vh, 640px);
}
.camera-dialog__view {
  min-height: 300px;
  background: #000;
}
.camera-dialog__video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  opacity: 0;
}
.camera-dialog__video--on {
  opacity: 1;
}
.camera-dialog__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
</style>
