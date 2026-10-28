// What a scan does to a product, per mode, with an undo handle for the session log.
import { reactive } from 'vue'
import { api } from '@/api'
import { t } from '@/i18n'
import { attempt, notify } from './notify'
import { consume, openProduct, purchase, type Undo } from './stockActions'
import type { Product, ScanMode } from '@/types'

export const SCAN_MODES: ScanMode[] = ['purchase', 'consume', 'open', 'spoil', 'shopping', 'lookup']
export const modeIcon: Record<ScanMode, string> = {
  purchase: 'mdi-cart-arrow-down',
  consume: 'mdi-silverware-fork-knife',
  open: 'mdi-package-variant-closed-remove',
  spoil: 'mdi-delete-variant',
  shopping: 'mdi-cart-plus',
  lookup: 'mdi-magnify',
}

export interface LogEntry {
  id: number
  at: Date
  name: string
  mode: ScanMode
  amount: number
  unit: string
  code?: string
  undo?: Undo
  undone?: boolean
}

/** The scan session log, kept while the app is open. */
export const scanLog = reactive<LogEntry[]>([])
let nextId = 1

export function logScan(entry: Omit<LogEntry, 'id' | 'at'>) {
  scanLog.unshift({ ...entry, id: nextId++, at: new Date() })
  if (scanLog.length > 30) scanLog.length = 30
}

/** Run the mode's action. Returns false when it failed. */
export async function runScanAction(
  product: Product,
  mode: ScanMode,
  amount: number,
  opts: { dueDate?: string | null; code?: string } = {},
): Promise<boolean> {
  let undo: Undo | false | undefined
  switch (mode) {
    case 'purchase':
      undo = await purchase(product, amount, { due_date: opts.dueDate || null })
      break
    case 'consume':
      undo = await consume(product, amount)
      break
    case 'spoil':
      undo = await consume(product, amount, true)
      break
    case 'open':
      undo = await openProduct(product, amount)
      break
    case 'shopping': {
      const added = await attempt(async () => {
        const lists = await api.shoppingLists()
        if (!lists.length) throw new Error(t.shopping.empty)
        return api.addShoppingItem(lists[0].id, { product_id: product.id, amount })
      })
      if (!added) return false
      notify(t.scan.added(product.name))
      undo = async () => {
        await attempt(() => api.deleteShoppingItem(added.id))
      }
      break
    }
    case 'lookup':
      undo = undefined
      break
  }
  if (undo === false) return false
  logScan({ name: product.name, mode, amount, unit: product.unit, code: opts.code, undo: undo || undefined })
  return true
}
