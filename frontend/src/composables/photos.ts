// Photos from the camera or the device. The Home Assistant app hands picked files over lazily (they can be
// empty or unreadable later), so a photo is read into memory right away, turned upright and scaled down.
import { t } from '@/i18n'

const MAX_EDGE = 2048
const QUALITY = 0.9

async function decode(blob: Blob): Promise<CanvasImageSource & { width: number; height: number }> {
  try {
    return await createImageBitmap(blob, { imageOrientation: 'from-image' })
  } catch {
    // Older browsers: let an <img> decode it.
    const url = URL.createObjectURL(blob)
    try {
      const img = new Image()
      img.src = url
      await img.decode()
      return img
    } finally {
      URL.revokeObjectURL(url)
    }
  }
}

function toJpeg(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error(t.photo.unreadable))), 'image/jpeg', QUALITY),
  )
}

function draw(source: CanvasImageSource, width: number, height: number): HTMLCanvasElement {
  const scale = Math.min(1, MAX_EDGE / Math.max(width, height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(width * scale)
  canvas.height = Math.round(height * scale)
  canvas.getContext('2d')!.drawImage(source, 0, 0, canvas.width, canvas.height)
  return canvas
}

function baseName(name: string) {
  return (name.replace(/\.[^.]+$/, '') || 'photo') + '.jpg'
}

/** A picked file as an in-memory JPEG (at most 2048 px). Throws with a readable message if it can't be used. */
export async function preparePhoto(file: File): Promise<File> {
  let bytes: ArrayBuffer
  try {
    bytes = await file.arrayBuffer()
  } catch {
    throw new Error(t.photo.unreadable)
  }
  if (!bytes.byteLength) throw new Error(t.photo.empty)
  const blob = new Blob([bytes], { type: file.type || 'image/jpeg' })
  let image: CanvasImageSource & { width: number; height: number }
  try {
    image = await decode(blob)
  } catch {
    // Not decodable here (e.g. HEIC outside Safari): send the original bytes; the server says if it can't read them.
    return new File([blob], file.name || 'photo', { type: blob.type })
  }
  const jpeg = await toJpeg(draw(image, image.width, image.height))
  if ('close' in image && typeof image.close === 'function') image.close()
  return new File([jpeg], baseName(file.name || 'photo'), { type: 'image/jpeg' })
}

/** The current frame of a playing video as a JPEG file. */
export async function captureFrame(video: HTMLVideoElement): Promise<File> {
  const jpeg = await toJpeg(draw(video, video.videoWidth, video.videoHeight))
  return new File([jpeg], `photo-${Date.now()}.jpg`, { type: 'image/jpeg' })
}
