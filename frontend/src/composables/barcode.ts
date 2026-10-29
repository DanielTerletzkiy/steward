// Barcode scanning: the browser's BarcodeDetector when it has one, else the zxing-wasm polyfill.
// The polyfill's WebAssembly file is bundled with the app (no CDN), so scanning works offline.
import { onBeforeUnmount } from 'vue'
import wasmUrl from 'zxing-wasm/reader/zxing_reader.wasm?url'

export interface Detector {
  detect(source: CanvasImageSource): Promise<{ rawValue: string; format: string }[]>
}

const WANTED = ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'code_39', 'itf', 'data_matrix', 'qr_code']

let pending: Promise<Detector> | null = null

type NativeDetectorClass = {
  new (opts?: { formats?: string[] }): Detector
  getSupportedFormats?: () => Promise<string[]>
}

async function create(): Promise<Detector> {
  const Native = (window as unknown as { BarcodeDetector?: NativeDetectorClass }).BarcodeDetector
  if (Native) {
    try {
      const supported = (await Native.getSupportedFormats?.()) ?? WANTED
      const formats = WANTED.filter((f) => supported.includes(f))
      if (formats.length) return new Native({ formats })
    } catch {
      // Fall through to the polyfill.
    }
  }
  const { BarcodeDetector, prepareZXingModule } = await import('barcode-detector/ponyfill')
  prepareZXingModule({
    overrides: {
      locateFile: (path: string, prefix: string) => (path.endsWith('.wasm') ? new URL(wasmUrl, window.location.href).href : prefix + path),
    },
  })
  return new BarcodeDetector({ formats: WANTED as never }) as unknown as Detector
}

export function getDetector(): Promise<Detector> {
  pending ??= create().catch((e) => {
    pending = null
    throw e
  })
  return pending
}

export const cameraAvailable = () => window.isSecureContext && !!navigator.mediaDevices?.getUserMedia

/**
 * Keyboard-wedge scanners type the code very fast and press Enter. Collect such bursts anywhere on the
 * page and report them as scans. Bursts typed into a field are ignored, unless `inFields` is set (the
 * kiosk page): then the field also gets the characters, and the caller clears it in `onCode`.
 */
export function useWedgeScanner(onCode: (code: string) => void, opts: { inFields?: boolean } = {}) {
  let buffer = ''
  let last = 0
  function onKey(e: KeyboardEvent) {
    const target = e.target as HTMLElement | null
    const inField = target && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
    if (inField && !opts.inFields) return
    const now = performance.now()
    if (now - last > 60) buffer = ''
    last = now
    if (e.key === 'Enter') {
      if (buffer.length >= 6) {
        e.preventDefault()
        e.stopPropagation()
        onCode(buffer)
      }
      buffer = ''
    } else if (e.key.length === 1) {
      buffer += e.key
    }
  }
  window.addEventListener('keydown', onKey, true)
  onBeforeUnmount(() => window.removeEventListener('keydown', onKey, true))
}
