import { reactive } from 'vue'

export interface Toast {
  id: number
  text: string
  color?: string
  timeout: number
  action?: { label: string; run: () => void | Promise<void> }
}

export const toasts = reactive<{ current: Toast | null; show: boolean }>({ current: null, show: false })
let nextId = 1

export function notify(text: string, opts: Partial<Omit<Toast, 'id' | 'text'>> = {}) {
  toasts.current = { id: nextId++, text, timeout: opts.action ? 6000 : 3500, ...opts }
  toasts.show = true
}

export function notifyError(e: unknown) {
  const msg = e instanceof Error ? e.message : String(e)
  notify(msg, { color: 'error', timeout: 6000 })
}

/** Run an async action and report errors as a snackbar. Returns undefined on failure. */
export async function attempt<T>(fn: () => Promise<T>): Promise<T | undefined> {
  try {
    return await fn()
  } catch (e) {
    notifyError(e)
    return undefined
  }
}
