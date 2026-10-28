// Equipment helpers: warranty chips and the debounced manual search.
import { onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { formatDate } from './format'
import type { Equipment, ManualHit } from '@/types'

export function warrantyChip(e: Pick<Equipment, 'warranty_status' | 'warranty_until'>) {
  const until = formatDate(e.warranty_until)
  switch (e.warranty_status) {
    case 'ending':
      return { color: 'warning', variant: 'tonal' as const, icon: 'mdi-shield-alert-outline', text: t.equipment.warranty.ending(until) }
    case 'expired':
      return { color: undefined, variant: 'outlined' as const, icon: 'mdi-shield-off-outline', text: t.equipment.warranty.expired, muted: true }
    case 'active':
      return { color: 'success', variant: 'tonal' as const, icon: 'mdi-shield-check-outline', text: t.equipment.warranty.active(until) }
    default:
      return null
  }
}

export function docIcon(contentType: string) {
  if (contentType === 'application/pdf') return 'mdi-file-pdf-box'
  if (contentType.startsWith('image/')) return 'mdi-file-image-outline'
  return 'mdi-file-document-outline'
}

export function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** Full-text search over manuals, debounced while typing. */
export function useManualSearch(equipmentId?: () => number | null | undefined) {
  const query = ref<string | null>('')
  const hits = shallowRef<ManualHit[]>([])
  const searching = ref(false)
  const searched = ref(false)
  const error = ref<string | null>(null)
  let timer: number | undefined
  let seq = 0

  async function run() {
    const q = (query.value ?? '').trim()
    const mine = ++seq
    if (q.length < 2) {
      hits.value = []
      searched.value = false
      searching.value = false
      return
    }
    searching.value = true
    try {
      const res = await api.searchManuals(q, equipmentId?.() ?? null)
      if (mine !== seq) return
      hits.value = res
      error.value = null
    } catch (e) {
      if (mine !== seq) return
      hits.value = []
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      if (mine === seq) {
        searching.value = false
        searched.value = true
      }
    }
  }

  watch(query, () => {
    window.clearTimeout(timer)
    timer = window.setTimeout(run, 350)
  })
  onBeforeUnmount(() => window.clearTimeout(timer))

  function now() {
    window.clearTimeout(timer)
    return run()
  }
  return { query, hits, searching, searched, error, now }
}
