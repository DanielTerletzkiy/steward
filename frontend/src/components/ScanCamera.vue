<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { t } from '@/i18n'
import { cameraAvailable, getDetector, type Detector } from '@/composables/barcode'

const emit = defineEmits<{ detected: [string] }>()

const video = ref<HTMLVideoElement | null>(null)
const running = ref(false)
const starting = ref(false)
const error = ref<string | null>(null)
const flash = ref(false)
const secure = cameraAvailable()

let stream: MediaStream | null = null
let detector: Detector | null = null
let timer: number | undefined
let lastCode = ''
let lastAt = 0

async function start() {
  if (running.value || starting.value) return
  error.value = null
  starting.value = true
  try {
    ;[detector, stream] = await Promise.all([
      getDetector(),
      navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false }),
    ])
    if (!video.value) throw new Error(t.scan.cameraUnavailable)
    video.value.srcObject = stream
    await video.value.play()
    running.value = true
    tick()
  } catch (e) {
    stop()
    const name = e instanceof DOMException ? e.name : ''
    error.value = name === 'NotAllowedError' ? t.scan.cameraDenied : name === 'NotFoundError' ? t.scan.cameraUnavailable : e instanceof Error ? e.message : String(e)
  } finally {
    starting.value = false
  }
}

function stop() {
  window.clearTimeout(timer)
  stream?.getTracks().forEach((track) => track.stop())
  stream = null
  if (video.value) video.value.srcObject = null
  running.value = false
}

async function tick() {
  if (!running.value || !detector || !video.value) return
  try {
    if (video.value.readyState >= 2) {
      const codes = await detector.detect(video.value)
      const code = codes[0]?.rawValue?.trim()
      const now = Date.now()
      if (code && (code !== lastCode || now - lastAt > 3000)) {
        lastCode = code
        lastAt = now
        flash.value = true
        window.setTimeout(() => (flash.value = false), 350)
        navigator.vibrate?.(60)
        emit('detected', code)
      }
    }
  } catch {
    // A frame that cannot be read; try the next one.
  }
  timer = window.setTimeout(tick, 180)
}

onBeforeUnmount(stop)
defineExpose({ start, stop })
</script>

<template>
  <v-sheet color="black" rounded="xl" class="camera position-relative overflow-hidden">
    <video ref="video" class="camera__video" :class="{ 'camera__video--on': running }" muted playsinline />
    <div v-if="running" class="camera__frame" :class="{ 'camera__frame--hit': flash }" />
    <div v-if="!running" class="camera__overlay text-center pa-6">
      <template v-if="!secure">
        <v-icon icon="mdi-lock-alert-outline" size="40" class="mb-2 opacity-80" />
        <div class="text-body-2" style="max-width: 360px">{{ t.scan.cameraNeedsHttps }}</div>
      </template>
      <template v-else>
        <v-icon icon="mdi-barcode-scan" size="44" class="mb-3 opacity-80" />
        <div v-if="error" class="text-body-2 text-error mb-3">{{ error }}</div>
        <v-btn color="primary" variant="flat" prepend-icon="mdi-camera-outline" :loading="starting" @click="start">{{ t.scan.startCamera }}</v-btn>
      </template>
    </div>
    <div v-if="running" class="camera__bar d-flex align-center px-3 py-2">
      <span class="text-caption text-white opacity-80">{{ t.scan.pointCamera }}</span>
      <v-spacer />
      <v-btn size="small" variant="tonal" color="white" prepend-icon="mdi-stop" @click="stop">{{ t.scan.stopCamera }}</v-btn>
    </div>
  </v-sheet>
</template>

<style scoped>
.camera {
  aspect-ratio: 4 / 3;
  width: 100%;
  color: #fff;
}
.camera__video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  opacity: 0;
}
.camera__video--on {
  opacity: 1;
}
.camera__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.camera__frame {
  position: absolute;
  left: 12%;
  right: 12%;
  top: 30%;
  bottom: 30%;
  border: 2px solid rgba(255, 255, 255, 0.85);
  border-radius: 12px;
  box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.25);
  transition: border-color 0.15s;
}
.camera__frame--hit {
  border-color: rgb(var(--v-theme-primary));
  border-width: 3px;
}
.camera__bar {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.6));
}
</style>
